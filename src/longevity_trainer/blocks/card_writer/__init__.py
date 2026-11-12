"""card_writer: Draft quiz cards on one topic from one pinned source, keep only those whose quote is really in the source and that pass the card checker.

See SPEC.md in this folder (ADR 0003).
"""

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, computed_field

from longevity_trainer.blocks.card_bank import ROOT, LongevityCard
from longevity_trainer.blocks.card_checker import (
    LEARNING_GOALS,
    CardVerdict,
    check_card,
)
from quizkit.blocks.base import BlockSpec
from quizkit.blocks.receipts import (
    Receipt,
    ensure_source,
    find_quote,
    load_source,
    to_key,
)
from quizkit.blocks.source_text import text_pages
from quizkit.claude import ClaudeError, ask_claude
from quizkit.download import http_get

BLOCK_SPEC = BlockSpec(
    name="card_writer",
    kind="agent",
    goal="Draft quiz cards on one topic from one pinned source, keep only those whose quote is really in the source and that pass the card checker.",
    inputs=[
        "topic",
        "source_id",
        "n",
        "ask",
        "model",
        "check",
        "taken_ids",
        "taken_questions",
        "sources_dir",
        "root",
        "fetch",
        "pages",
    ],
    outputs=[
        "write_cards",
        "Draft",
        "Drop",
        "WriterReport",
        "PROMPT_VERSION",
        "slug",
        "ASKS",
        "REQUIRED_ASKS",
    ],
)

PROMPT_VERSION = "4"
SOURCES_DIR = ROOT / "data" / "sources"
MAX_SOURCE_CHARS = 200_000
ASKS = ("what", "how", "how_sure", "catch")
REQUIRED_ASKS = {"what", "how", "how_sure"}  # rule 1 (never names alone), rule 2
try:
    LEARNING_GOALS_TEXT = LEARNING_GOALS.read_text("utf-8")
except FileNotFoundError as err:  # a writer without its standard must not run
    raise RuntimeError(f"{LEARNING_GOALS} is missing (the question rules)") from err

SYSTEM = f"""\
You write quiz cards for someone learning longevity science. This is their \
standard for a good question, which you must follow:

{LEARNING_GOALS_TEXT}

Your task: write cards on ONE topic, using ONLY the source text you are given.
- Every card's quote must be copied EXACTLY, character for character, from the source text (a script checks it): one to three consecutive sentences. Never paraphrase the quote.
- If the source text is split into parts marked [page N], each quote must come from inside one page: a quote that runs across a page break can't be found.
- THE QUOTE ALONE MUST BACK THE WHOLE CARD. A strict checker will reject any card whose answer, or whose question, states a fact the quote doesn't. So:
  - keep each answer to ONE short claim, taken from the quote; never add facts from elsewhere in the source or from your own knowledge;
  - the question must not assert anything the quote doesn't say (if the quote doesn't name the drug, the trial or the population, pick a quote that does, or leave it out of the question);
  - a plain-English paraphrase of the quote in the answer is fine;
  - avoid open lists ("which outcomes", "what limitations", "key messages"): the question must have one clear answer, and if the quote lists several equally right items, either ask for one of them and accept each, or ask a narrower question.
- Cover the five questions per topic except the trend one: what is it, how does \
it work, how sure are we, what's the catch. Mark each card's "asks" as what, how, \
how_sure or catch.
- A how_sure answer names the species or population (mice, healthy people, \
patients) and doesn't oversell.
- No trivia: no sample sizes, p-values, registry numbers or exact dates.
- Each question must stand alone: never "the trial", "the authors", "this study" \
or "Figure 2"; name the thing.
- One clear right answer per question; list close alternatives in answers.
- No trend or popularity questions.
- kind: name (the answer is a name), fact (a short fact), term (define a term), \
explain (a sentence or two on how or why)."""

SCHEMA = {
    "type": "object",
    "properties": {
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "asks": {"type": "string", "enum": list(ASKS)},
                    "kind": {
                        "type": "string",
                        "enum": ["name", "fact", "term", "explain"],
                    },
                    "question": {"type": "string"},
                    "answers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                    "quote": {"type": "string"},
                },
                "required": ["asks", "kind", "question", "answers", "quote"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["cards"],
    "additionalProperties": False,
}


class Draft(BaseModel):
    """One card as Claude drafted it (not yet checked)."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    asks: Literal["what", "how", "how_sure", "catch"]
    kind: Literal["name", "fact", "term", "explain"]
    question: str
    answers: list[str] = Field(min_length=1)
    quote: str


class Drop(BaseModel):
    """A draft that didn't survive, and why."""

    model_config = ConfigDict(frozen=True)

    question: str
    gate: Literal["shape", "quote", "repeat", "checker"]
    reason: str


class WriterReport(BaseModel):
    """What happened to the drafts, and whether the writer bar is met."""

    model_config = ConfigDict(frozen=True)

    drafted: int
    kept: int
    dropped_shape: int
    dropped_quote: int
    dropped_repeat: int
    dropped_checker: int
    checker_errors: int
    asks_kept: list[str]
    model: str
    prompt_version: str = PROMPT_VERSION

    @computed_field  # in model_dump(), so a saved report keeps its verdict
    @property
    def passed(self) -> bool:
        return (
            self.drafted > 0
            and self.dropped_quote <= self.drafted * 0.2
            # coverage of the asks is a goal for the topic, over runs (--add)
            and self.kept >= 1
        )


class WriterResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    kept: list[LongevityCard]
    drops: list[Drop]
    report: WriterReport


def slug(text: str) -> str:
    """Lower case, letters/digits/hyphens: 'Epigenetic clocks!' -> 'epigenetic-clocks'."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _norm(question: str) -> str:
    return " ".join(question.lower().split())


def _source_text(
    source_id: str,
    sources_dir: Path,
    root: Path,
    fetch: Callable[[str], bytes],
    pages: tuple[int, int] | None = None,
) -> tuple[str, list[str], list[tuple[int, str]], str]:
    """(title, every page's text, chosen (page number, text) pairs, prompt text)
    of a pinned source; raises before any Claude call."""
    source = load_source(Path(sources_dir) / f"{source_id}.json")
    if source.id != source_id:
        raise ValueError(f"{source_id}.json is for {source.id!r}")
    path = ensure_source(source, root, fetch)
    every = text_pages(path, source.format)
    numbered = list(enumerate(every, 1))
    if pages is not None:
        first, last = pages
        if first < 1 or last < first or last > len(numbered):
            raise ValueError(
                f"pages {first}-{last} don't fit: {source_id} has {len(numbered)} pages"
            )
        numbered = numbered[first - 1 : last]
    if len(numbered) == 1:
        text = numbered[0][1]
    else:  # mark page breaks, so quotes stay inside one page (find_quote is per page)
        text = "\n\n".join(f"[page {i}]\n{page}" for i, page in numbered)
    if len(text) > MAX_SOURCE_CHARS:
        raise ValueError(
            f"source too long ({len(text):,} characters, max {MAX_SOURCE_CHARS:,})"
        )
    return source.title, every, numbered, text


def _drafts(reply_text: str) -> list[Draft]:
    try:
        data = json.loads(reply_text)
        if not isinstance(data, dict) or not isinstance(data.get("cards"), list):
            raise TypeError("no 'cards' list")
        return [Draft.model_validate(card) for card in data["cards"]]
    except (ValueError, TypeError) as err:  # bad JSON; ValidationError is a ValueError
        raise ClaudeError(f"bad reply: {str(err).splitlines()[0]}") from err


def write_cards(
    topic: str,
    source_id: str,
    n: int = 8,
    ask: Callable[..., object] = ask_claude,
    model: str = "sonnet",
    check: Callable[[LongevityCard], CardVerdict] = check_card,
    taken_ids: set[str] | None = None,
    taken_questions: set[str] | None = None,
    sources_dir: Path = SOURCES_DIR,
    root: Path = ROOT,
    fetch: Callable[[str], bytes] = http_get,
    pages: tuple[int, int] | None = None,
) -> WriterResult:
    """Draft `n` cards, run them through the gates, return what survived and why."""
    topic_slug = slug(topic)
    if not topic_slug:
        raise ValueError(f"topic {topic!r} has no letters or digits")
    if not 1 <= n <= 20:
        raise ValueError(f"n must be 1-20, not {n}")
    title, every, chosen, text = _source_text(
        source_id, sources_dir, root, fetch, pages
    )
    keys = [to_key(page) for _, page in chosen]
    all_keys = [to_key(page) for page in every]
    known = ""
    if taken_questions:
        listed = "\n".join(f"- {q}" for q in sorted(taken_questions))
        known = (
            "Questions already in the bank: don't ask any of these again, "
            f"even in other words; ask about other facts:\n{listed}\n\n"
        )
    reply = ask(
        f"Topic: {topic}\nNumber of cards: {n}\nSource: {title}\n\n{known}"
        f"Source text:\n{text}",
        model=model,
        system=SYSTEM,
        json_schema=SCHEMA,
    )
    drafts = _drafts(reply.text)[:n]

    taken = set(taken_ids or ())
    survivors: list[tuple[Draft, LongevityCard]] = []
    drops: list[Drop] = []
    seen: set[str] = set()
    in_bank = {_norm(q) for q in taken_questions or ()}
    checker_errors = 0
    for number, draft in enumerate(drafts, start=1):
        provisional = f"{topic_slug}-draft-{number}"
        try:
            receipt = Receipt(source=source_id, quote=draft.quote, page=1)
            card = LongevityCard(
                id=provisional,
                kind=draft.kind,
                topic=topic,
                question=draft.question,
                answers=draft.answers,
                receipt=receipt,
            )
        except ValidationError as err:
            reason = err.errors()[0]
            where = ".".join(str(p) for p in reason["loc"]) or "card"
            drops.append(
                Drop(
                    question=draft.question,
                    gate="shape",
                    reason=f"{where}: {reason['msg']}",
                )
            )
            continue
        if find_quote(draft.quote, keys) is None:  # must be on a chosen page
            drops.append(
                Drop(
                    question=draft.question,
                    gate="quote",
                    reason=f"quote not found in {source_id}",
                )
            )
            continue
        card = card.model_copy(
            update={
                "receipt": receipt.model_copy(
                    update={"page": find_quote(draft.quote, all_keys)}
                )
            }
        )
        if _norm(card.question) in in_bank:
            drops.append(
                Drop(
                    question=draft.question,
                    gate="repeat",
                    reason="already in the bank",
                )
            )
            continue
        if _norm(card.question) in seen:
            drops.append(
                Drop(
                    question=draft.question,
                    gate="repeat",
                    reason="same question as an earlier card",
                )
            )
            continue
        try:
            verdict = check(card)
        except ClaudeError as err:
            checker_errors += 1
            drops.append(
                Drop(
                    question=draft.question,
                    gate="checker",
                    reason=f"checker error: {err}",
                )
            )
            continue
        if not verdict.ok:
            drops.append(
                Drop(
                    question=draft.question,
                    gate="checker",
                    reason=f"rules {verdict.rules}: {verdict.reason}",
                )
            )
            continue
        seen.add(_norm(card.question))  # only kept questions block later repeats
        survivors.append((draft, card))

    kept: list[LongevityCard] = []
    counters: dict[str, int] = {}
    for draft, card in survivors:
        stem = f"{topic_slug}-{draft.asks.replace('_', '-')}"
        while True:
            counters[stem] = counters.get(stem, 0) + 1
            card_id = f"{stem}-{counters[stem]}"
            if card_id not in taken:
                break
        taken.add(card_id)
        kept.append(card.model_copy(update={"id": card_id}))

    def count(gate: str) -> int:
        return sum(d.gate == gate for d in drops)

    report = WriterReport(
        drafted=len(drafts),
        kept=len(kept),
        dropped_shape=count("shape"),
        dropped_quote=count("quote"),
        dropped_repeat=count("repeat"),
        dropped_checker=count("checker"),
        checker_errors=checker_errors,
        asks_kept=sorted({draft.asks for draft, _ in survivors}),
        model=model,
    )
    return WriterResult(kept=kept, drops=drops, report=report)
