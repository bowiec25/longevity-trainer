"""marking: Mark a typed answer with Claude when the answer list says no: word-level for names and facts, main-idea for explanations.

See SPEC.md in this folder (ADR 0003).
"""

import time
from collections.abc import Callable
from pathlib import Path
from typing import get_args

from pydantic import BaseModel, ConfigDict, Field

from longevity_trainer.blocks.card_bank import ROOT, Kind, LongevityCard
from quizkit.blocks.base import BlockSpec
from quizkit.blocks.engine import QuizSession
from quizkit.blocks.jsonl_loader import load_jsonl_file
from quizkit.blocks.judge import WORD_RUBRIC, ClaudeJudge
from quizkit.blocks.judge.eval import EvalReport, ScoreItem, score, verdict_mark
from quizkit.claude import ClaudeError, ask_claude
from quizkit.models import Judge, Question, Verdict

BLOCK_SPEC = BlockSpec(
    name="marking",
    kind="agent",
    goal="Mark a typed answer with Claude when the answer list says no: word-level for names and facts, main-idea for explanations.",
    inputs=[
        "question",
        "typed",
        "cache_file",
        "ask",
        "before_asking",
        "cases",
        "cards",
    ],
    outputs=[
        "make_judge",
        "SUBJECT",
        "CONCEPT_RUBRIC",
        "Verdict",
        "MarkingCase",
        "MARKING_EVAL_FILE",
        "load_marking_cases",
        "check_card_ids",
        "run_marking_eval",
    ],
)

SUBJECT = (
    "Longevity science: ageing biology, drugs, supplements, lifestyle and how strong "
    "the evidence is. The learner types a short answer or an explanation in their "
    "own words."
)

CONCEPT_RUBRIC = """\
would a fair teacher accept it as showing the learner understood the key idea of \
the model answer?

Accept:
- the learner's own words, if the key idea (the mechanism, or the main point of the \
model answer) is there
- a simpler wording that still gets the key idea right, as long as every part \nthe question asks for is there
- extra detail, as long as it is correct
- small spelling or grammar slips

Reject:
- a wrong or missing key idea
- a related but different mechanism or thing
- an answer that covers only some of the parts the question asks for (for \nexample one of three tests)
- anything stated that contradicts the model answer
- moving a finding to a different species or group (mice to people, patients \nto healthy people)
- overselling: claiming more certainty or benefit than the model answer (for \
example "reverses ageing" when the answer says "unproven in people")
- a vague answer that would fit many different questions

If you are unsure, say it is wrong: accepting a wrong answer teaches a mistake."""

WORD_KINDS = {"name", "fact"}
CONCEPT_KINDS = {"term", "explain"}
CONCEPT_MAX_CHARS = 400
MAX_FAILURES = 2  # Claude failing this often in a row switches marking off for the run

# Every card kind needs a marking rule: fail at import, not mid-quiz.
_missing = set(get_args(Kind)) - WORD_KINDS - CONCEPT_KINDS
if _missing:
    raise ImportError(f"no marking rule for card kinds {sorted(_missing)}")


def make_judge(
    cache_file: Path | None = None,
    ask: Callable[..., object] = ask_claude,
    before_asking: Callable[[], None] | None = None,
) -> Judge:
    """This quiz's judge: word-level for names and facts, main-idea for explanations.

    One judge for the run: Claude failing MAX_FAILURES times in a row (on either
    route) switches it off, so an offline quiz doesn't wait on every answer."""
    failures = 0

    def asked(prompt: str, **kwargs: object) -> object:
        nonlocal failures
        if failures >= MAX_FAILURES:
            raise ClaudeError("Claude failed twice in a row: marking off for this run")
        if before_asking is not None:
            before_asking()
        try:
            reply = ask(prompt, **kwargs)
        except ClaudeError:
            failures += 1
            raise
        failures = 0
        return reply

    def judge_with(rubric: str, **limits: int) -> ClaudeJudge:
        return ClaudeJudge(
            SUBJECT,
            cache_file=cache_file,
            rubric=rubric,
            ask=asked,
            **limits,
        )

    words = judge_with(WORD_RUBRIC)
    concepts = judge_with(CONCEPT_RUBRIC, max_chars=CONCEPT_MAX_CHARS)

    def judge(question: Question, typed: str) -> Verdict:
        if question.mode in WORD_KINDS:
            return words(question, typed)
        if question.mode in CONCEPT_KINDS:
            return concepts(question, typed)
        raise ValueError(f"no marking rule for card kind {question.mode!r}")

    return judge


# --- the eval: how often Claude's marking agrees with the user's labels ----------

MARKING_EVAL_FILE = ROOT / "tests" / "data" / "marking_eval.jsonl"


class MarkingCase(BaseModel):
    """One answer the user labelled: should it count as right?"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    card_id: str = Field(min_length=1)
    typed: str
    expected: bool
    why: str = ""

    def model_post_init(self, _context: object) -> None:
        if not self.typed.strip():
            raise ValueError("typed must not be blank")


def load_marking_cases(path: Path = MARKING_EVAL_FILE) -> list[MarkingCase]:
    """One case per non-blank line; a bad line raises ValueError with its number."""
    return load_jsonl_file(path, MarkingCase, id_field=None, what="marking eval cases")


def check_card_ids(cases: list[MarkingCase], cards: list[LongevityCard]) -> None:
    """Raise ValueError naming every case's card_id that isn't in the bank."""
    known = {c.id for c in cards}
    unknown = [case.card_id for case in cases if case.card_id not in known]
    if unknown:
        raise ValueError(f"eval cases name cards not in the bank: {', '.join(unknown)}")


def _mark_as_quiz(
    card: LongevityCard, typed: str, judge: Judge
) -> tuple[bool | None, str]:
    """Mark like the quiz: the answer list first, the judge only when it says wrong."""
    attempt = QuizSession([card.to_question()], judge=judge).answer(typed)
    if attempt.verdict is not None:
        return verdict_mark(attempt.verdict)
    # No verdict means the answer list said yes: the quiz asks the judge for every
    # wrong, non-blank answer, and MarkingCase never has a blank one.
    return True, f"accepted by the answer list ({attempt.grade.matched!r})"


def run_marking_eval(
    cases: list[MarkingCase],
    cards: list[LongevityCard],
    judge: Judge,
    show: Callable[[str], None] = print,
    clock: Callable[[], float] = time.perf_counter,
) -> EvalReport:
    """Mark every case and count agreement with the labels (quizkit's EvalReport)."""
    check_card_ids(cases, cards)
    by_id = {c.id: c for c in cards}
    items = [
        ScoreItem(
            case.card_id,
            case.typed,
            case.expected,
            lambda case=case: _mark_as_quiz(by_id[case.card_id], case.typed, judge),
        )
        for case in cases
    ]
    return score(items, show=show, clock=clock)
