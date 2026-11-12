"""marking: Mark a typed answer with Claude when the answer list says no: word-level for names and facts, main-idea for explanations.

See SPEC.md in this folder (ADR 0003).
"""

from collections.abc import Callable
from pathlib import Path
from typing import get_args

from longevity_trainer.blocks.card_bank import Kind
from quizkit.blocks.base import BlockSpec
from quizkit.blocks.judge import WORD_RUBRIC, ClaudeJudge
from quizkit.claude import ClaudeError, ask_claude
from quizkit.models import Judge, Question, Verdict

BLOCK_SPEC = BlockSpec(
    name="marking",
    kind="agent",
    goal="Mark a typed answer with Claude when the answer list says no: word-level for names and facts, main-idea for explanations.",
    inputs=["question", "typed", "cache_file", "ask", "before_asking"],
    outputs=["make_judge", "SUBJECT", "CONCEPT_RUBRIC", "Verdict"],
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
