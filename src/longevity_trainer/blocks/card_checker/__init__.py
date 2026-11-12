"""card_checker: Check one card and its quote against the question rules in docs/LEARNING_GOALS.md, and score that check on the labelled card exam.

See SPEC.md in this folder (ADR 0003).
"""

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    computed_field,
    field_validator,
    model_validator,
)

from longevity_trainer.blocks.card_bank import ROOT, LongevityCard
from quizkit.blocks.base import BlockSpec
from quizkit.claude import ClaudeError, ask_claude

BLOCK_SPEC = BlockSpec(
    name="card_checker",
    kind="agent",
    goal="Check one card and its quote against the question rules in docs/LEARNING_GOALS.md, and score that check on the labelled card exam.",
    inputs=["card", "ask", "model", "cases_file", "show"],
    outputs=[
        "check_card",
        "CardVerdict",
        "RULES_TEXT",
        "PROMPT_VERSION",
        "ExamCase",
        "load_exam",
        "run_exam",
        "ExamReport",
        "MAX_FALSE_FLAG_SHARE",
        "MAX_RULES_NAMED",
    ],
)

PROMPT_VERSION = "2"
LEARNING_GOALS = ROOT / "docs" / "LEARNING_GOALS.md"
EXAM_FILE = ROOT / "tests" / "data" / "card_eval.jsonl"
HOLDOUT_FILE = ROOT / "tests" / "data" / "card_eval_holdout.jsonl"  # never tuned on
CHECKED_RULES = (2, 3, 4, 5, 6)  # rule 1 is per topic, rule 7 is for trend cards
# A wrongly rejected good card costs one redraft; a bad card let through teaches a
# mistake. So the bar allows a few false flags but no bad card through (user, 2026-11-12).
# Revisit when tuning (docs/FUTURE.md): 1/3 matches what Haiku does today.
MAX_FALSE_FLAG_SHARE = 1 / 3  # of the good cards
MAX_RULES_NAMED = (
    3  # a verdict naming more rules than this is a shotgun, not a diagnosis
)


def _rules_section(text: str) -> str:
    """Section 2 of LEARNING_GOALS.md: its heading up to the next `## ` heading."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("## 2.")), None)
    if start is None:
        raise RuntimeError(f"{LEARNING_GOALS.name} has no '## 2.' section (the rules)")
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    return "\n".join(lines[start:end]).strip()


try:
    RULES_TEXT = _rules_section(LEARNING_GOALS.read_text("utf-8"))
except FileNotFoundError as err:  # a checker without its rules must not run
    raise RuntimeError(f"{LEARNING_GOALS} is missing (the rules)") from err

SYSTEM = f"""\
You are a strict but fair reviewer of quiz cards for someone learning longevity \
science. A card has a question, the accepted answers, and a quote from a trusted \
source that backs the answer. Decide whether the card is good enough to teach.

The rules for a good question:

{RULES_TEXT}

How to judge:
- Judge only rules 2, 3, 4, 5 and 6. Rule 1 is about a whole topic and rule 7 is \
about trend cards; ignore both.
- Judge from the card and the quote alone. The quote is an excerpt about the \
card's topic: words like "it" or "these effects" refer to what the source is \
discussing, so don't fail a card because the excerpt doesn't repeat the topic's name.
- The quote is already verified to be word for word in a trusted source. Your job \
on rule 3 is whether the quote BACKS the card: every factual claim in the answer, \
and any fact the question asserts, must be stated by the quote. A plain-English \
paraphrase or simplification of what the quote says is fine (the learner is not an \
expert); a stronger claim, a wider group or an added fact is not. A question with \
several right answers where only one is accepted also breaks rule 3, as does a \
claim that won't stay true for about 2 years ("so far", "the newest").
- Rule 2 applies when the card claims an effect or how well something works: the \
answer must say in whom (mice, healthy people, patients). A card about how a drug \
works in cells, or what it is used for, needs no population.
- Rule 4: what a trial tested, what it found, what it meant for the field, and its \
main limitation are worth knowing. Trivia is the detail: sample sizes, p-values, \
registry numbers, exact dates, subgroup statistics nobody would quote.
- Rule 6: a card may name a well-known trial or term (PEARL, mTOR) as long as the \
question makes sense to someone who hasn't read this particular paper; "the trial", \
"this group", "the authors" or "Figure 2" do not.
- A card can break more than one rule: list every rule it breaks.
- If you are unsure, fail the card: a bad card teaches a mistake.

Reply with ok (true if it breaks none of rules 2-6), rules (the numbers it \
breaks; empty if ok), and reason (one or two plain sentences)."""

SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "rules": {
            "type": "array",
            "items": {"type": "integer", "enum": list(CHECKED_RULES)},
        },
        "reason": {"type": "string"},
    },
    "required": ["ok", "rules", "reason"],
    "additionalProperties": False,
}


class CardVerdict(BaseModel):
    """The checker's decision on one card."""

    # strict: "false" is not False and "3" is not 3 (never guess a verdict)
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    ok: bool
    rules: list[int]
    reason: str = Field(min_length=1)

    @field_validator("rules")
    @classmethod
    def once_each(cls, rules: list[int]) -> list[int]:
        return list(dict.fromkeys(rules))  # de-duplicate, keep order

    @model_validator(mode="after")
    def consistent(self) -> "CardVerdict":
        if not self.reason.strip():
            raise ValueError("reason is empty")
        if any(rule not in CHECKED_RULES for rule in self.rules):
            raise ValueError(f"rules must be from {CHECKED_RULES}")
        if self.ok and self.rules:
            raise ValueError("ok but rules listed")
        if not self.ok and not self.rules:
            raise ValueError("not ok but no rule named")
        return self


def _prompt(card: LongevityCard) -> str:
    answers = "\n".join(f"- {a}" for a in card.answers)
    return (
        f"Card kind: {card.kind}\n"
        f"Topic: {card.topic}\n"
        f"Question: {card.question}\n"
        f"Accepted answers:\n{answers}\n"
        f"Source: {card.receipt.source}\n"
        f"Quote: {card.receipt.quote}"
    )


def check_card(
    card: LongevityCard,
    ask: Callable[..., object] = ask_claude,
    model: str = "haiku",
) -> CardVerdict:
    """Claude's verdict on one card. Raises ClaudeError if it can't give a valid one."""
    reply = ask(_prompt(card), model=model, system=SYSTEM, json_schema=SCHEMA)
    try:
        return CardVerdict.model_validate(json.loads(reply.text))
    except (ValueError, TypeError) as err:  # bad JSON, ValidationError: both ValueError
        first = str(err).splitlines()[0]
        raise ClaudeError(f"bad reply: {first}") from err


class ExamCase(BaseModel):
    """One labelled card in the exam."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    expected: Literal["pass", "fail"]
    rules: list[int]
    why: str = Field(min_length=1)
    origin: str = Field(min_length=1)
    card: LongevityCard

    @model_validator(mode="after")
    def consistent(self) -> "ExamCase":
        if any(rule not in CHECKED_RULES for rule in self.rules):
            raise ValueError(f"rules must be from {CHECKED_RULES}")
        if self.expected == "pass" and self.rules:
            raise ValueError("a pass case lists rules")
        if self.expected == "fail" and not self.rules:
            raise ValueError("a fail case lists no rules")
        return self


def load_exam(cases_file: Path = EXAM_FILE) -> list[ExamCase]:
    """The exam's cases; a bad line raises ValueError naming its line number."""
    cases = []
    text = Path(cases_file).read_text("utf-8-sig")
    for number, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            continue
        try:
            cases.append(ExamCase.model_validate(json.loads(line)))
        except (ValueError, ValidationError) as err:
            first = str(err).splitlines()[0]
            raise ValueError(f"{Path(cases_file).name} line {number}: {first}") from err
        if [c.id for c in cases].count(cases[-1].id) > 1:
            raise ValueError(
                f"{Path(cases_file).name} line {number}: repeated id {cases[-1].id!r}"
            )
    return cases


class ExamReport(BaseModel):
    """How the checker did on the exam, and whether it meets the bar."""

    model_config = ConfigDict(frozen=True)

    total: int
    bad_cards: int
    caught: int
    right_rule: int
    false_flags: int
    errors: int
    seconds: float
    model: str = ""
    prompt_version: str = PROMPT_VERSION

    @computed_field  # included in model_dump(), so a saved report keeps its verdict
    @property
    def passed(self) -> bool:
        return (
            self.total > 0
            and self.errors == 0
            and self.caught == self.bad_cards
            and self.right_rule >= self.bad_cards - 2
            and self.false_flags <= (self.total - self.bad_cards) * MAX_FALSE_FLAG_SHARE
        )


def run_exam(
    cases: list[ExamCase],
    check: Callable[[LongevityCard], CardVerdict] = check_card,
    show: Callable[[str], None] = print,
    model: str = "",
    clock: Callable[[], float] = time.perf_counter,
) -> ExamReport:
    """Check every case once, print a line each, and return the report."""
    start = clock()
    caught = right_rule = false_flags = errors = 0
    for case in cases:
        try:
            verdict = check(case.card)
        except Exception as err:  # noqa: BLE001 (one odd failure mustn't lose a paid run)
            errors += 1
            show(f"! {case.id}: error ({type(err).__name__}: {err})")
            continue
        got = "pass" if verdict.ok else f"fail {verdict.rules}"
        if case.expected == "fail":
            if verdict.ok:
                show(
                    f"✗ {case.id}: expected fail {case.rules}, got pass: {verdict.reason}"
                )
                continue
            caught += 1
            # right if it names one of the case's rules, without naming nearly
            # all of them (a shotgun verdict must not score)
            named = set(verdict.rules)
            if named & set(case.rules) and len(named) <= MAX_RULES_NAMED:
                right_rule += 1
                show(f"✓ {case.id}: {got}")
            else:
                show(
                    f"~ {case.id}: caught, but expected rule {case.rules}, got {got}: {verdict.reason}"
                )
        elif verdict.ok:
            show(f"✓ {case.id}: pass")
        else:
            false_flags += 1
            show(f"✗ {case.id}: expected pass, got {got}: {verdict.reason}")
    bad = sum(case.expected == "fail" for case in cases)
    report = ExamReport(
        total=len(cases),
        bad_cards=bad,
        caught=caught,
        right_rule=right_rule,
        false_flags=false_flags,
        errors=errors,
        seconds=round(clock() - start, 1),
        model=model,
    )
    show(
        f"\n{report.model or 'checker'} (prompt v{report.prompt_version}): "
        f"caught {caught}/{bad} bad cards ({right_rule} with the right rule), "
        f"{false_flags} good cards wrongly flagged, {errors} errors, "
        f"{report.seconds}s -> {'PASSED' if report.passed else 'NOT PASSED'}"
    )
    return report
