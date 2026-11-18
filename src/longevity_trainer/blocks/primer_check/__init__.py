"""primer_check: Tag each card easy or hard: easy when the user's primer states the card's fact, proven by a word-for-word primer passage

See SPEC.md in this folder (ADR 0003, ADR 0010).
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from longevity_trainer.blocks.card_bank import LongevityCard
from quizkit.blocks.base import BlockSpec
from quizkit.blocks.receipts import find_quote, to_key
from quizkit.blocks.source_text import text_pages
from quizkit.claude import ClaudeError, ask_claude

BLOCK_SPEC = BlockSpec(
    name="primer_check",
    kind="agent",
    goal="Tag each card easy or hard: easy when the user's primer states the card's fact, proven by a word-for-word primer passage",
    inputs=["cards", "primer_pages", "ask", "model", "path"],
    outputs=["PRIMER_FILE", "load_primer", "tag_cards", "TagResult", "PROMPT_VERSION"],
)

PROMPT_VERSION = "1"
# The user's own primer: outside the repo, never committed (ADR 0004, ADR 0010)
PRIMER_FILE = (
    Path.home()
    / "Desktop"
    / "Longevity_Platform_Blueprint"
    / "1_DOCS"
    / "longevity_trends_primer.pdf"
)

Difficulty = Literal["easy", "hard"]
NOT_IN_PRIMER = "not in the primer"
QUOTE_NOT_FOUND = "primer quote not found"
NO_VERDICT = "no verdict"
# A quote's key (letters/digits only) must be this long to prove anything: a word
# like "mTOR" is found somewhere in any primer (receipts use 20 for the same reason)
MIN_QUOTE_KEY = 30

SYSTEM = """\
You check quiz cards against the learner's primer (their own study notes). For \
each card, decide whether the primer states the fact the card's answer gives: \
the same claim, not merely the same topic. A paraphrase in the primer counts; a \
related but different fact does not.
- If it does: in_primer is true, and primer_quote is 1 to 3 consecutive sentences \
copied EXACTLY, character for character, from the primer (a script checks it). \
Never paraphrase the quote. Keep it inside one [page N] part.
- If it doesn't: in_primer is false and primer_quote is "".
- If you are unsure, answer false: hard is the safe side.
Give one verdict per card, using its id."""

SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "card_id": {"type": "string"},
                    "in_primer": {"type": "boolean"},
                    "primer_quote": {"type": "string"},
                },
                "required": ["card_id", "in_primer", "primer_quote"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["verdicts"],
    "additionalProperties": False,
}


class _Verdict(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    card_id: str
    in_primer: bool
    primer_quote: str


class TagResult(BaseModel):
    """Each card's difficulty, and why each hard card is hard."""

    model_config = ConfigDict(frozen=True)

    difficulty: dict[str, Difficulty]
    reasons: dict[str, str]
    model: str
    prompt_version: str = PROMPT_VERSION


def load_primer(path: Path | None = None) -> list[str]:
    """The primer's pages as text (default file: PRIMER_FILE, looked up now)."""
    path = PRIMER_FILE if path is None else Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"primer not found: {path}")
    return text_pages(path, "pdf")


def _prompt(cards: list[LongevityCard], primer_pages: list[str]) -> str:
    listed = "\n\n".join(
        f"id: {c.id}\nquestion: {c.question}\naccepted answers: " + "; ".join(c.answers)
        for c in cards
    )
    primer = "\n\n".join(
        f"[page {number}]\n{page}" for number, page in enumerate(primer_pages, 1)
    )
    return f"Cards:\n\n{listed}\n\nThe primer:\n\n{primer}"


def _verdicts(reply_text: str) -> list[_Verdict]:
    try:
        data = json.loads(reply_text)
        if not isinstance(data, dict) or not isinstance(data.get("verdicts"), list):
            raise TypeError("no 'verdicts' list")
        return [_Verdict.model_validate(v) for v in data["verdicts"]]
    except (ValueError, TypeError, ValidationError) as err:
        raise ClaudeError(f"bad reply: {str(err).splitlines()[0]}") from err


def tag_cards(
    cards: list[LongevityCard],
    primer_pages: list[str],
    ask: Callable[..., object] = ask_claude,
    model: str = "sonnet",
) -> TagResult:
    """One Claude call for all the cards; easy only with a primer quote code finds."""
    if not cards:
        return TagResult(difficulty={}, reasons={}, model=model)
    reply = ask(
        _prompt(cards, primer_pages), model=model, system=SYSTEM, json_schema=SCHEMA
    )
    by_id: dict[str, _Verdict] = {}
    for verdict in _verdicts(reply.text):
        by_id.setdefault(verdict.card_id, verdict)  # a repeated id: the first counts
    keys = [to_key(page) for page in primer_pages]
    difficulty: dict[str, Difficulty] = {}
    reasons: dict[str, str] = {}
    for card in cards:
        verdict = by_id.get(card.id)
        if verdict is None:
            reason = NO_VERDICT
        elif not verdict.in_primer:
            reason = NOT_IN_PRIMER
        elif (
            len(to_key(verdict.primer_quote)) < MIN_QUOTE_KEY
            or find_quote(verdict.primer_quote, keys) is None
        ):
            reason = QUOTE_NOT_FOUND
        else:
            difficulty[card.id] = "easy"
            continue
        difficulty[card.id] = "hard"
        reasons[card.id] = reason
    return TagResult(difficulty=difficulty, reasons=reasons, model=model)
