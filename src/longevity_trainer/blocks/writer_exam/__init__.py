"""writer_exam: Score the card writer on a fixed list of writing jobs: drafts kept, why the rest died, empty jobs and invented quotes, against a bar.

See SPEC.md in this folder (ADR 0003).
"""

from collections.abc import Callable
from fractions import Fraction
from pathlib import Path

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
from longevity_trainer.blocks.card_checker import (
    PROMPT_VERSION as CHECKER_PROMPT_VERSION,
)
from longevity_trainer.blocks.card_checker import CardVerdict, check_card
from longevity_trainer.blocks.card_writer import ASKS, PROMPT_VERSION, Drop, write_cards
from quizkit.blocks.base import BlockSpec

BLOCK_SPEC = BlockSpec(
    name="writer_exam",
    kind="script",
    goal="Score the card writer on a fixed list of writing jobs: drafts kept, why the rest died, empty jobs and invented quotes, against a bar.",
    inputs=[
        "load_jobs",
        "run_writer_exam",
        "write",
        "check",
        "primer",
        "show",
        "model",
    ],
    outputs=[
        "ExamJob",
        "JobScore",
        "WriterExamReport",
        "JOBS_FILE",
        "MIN_KEPT_SHARE",
        "MAX_EMPTY_JOBS",
    ],
)

JOBS_FILE = ROOT / "tests" / "data" / "writer_exam.jsonl"
MIN_KEPT_SHARE = Fraction(2, 5)  # of all drafts (user, 2026-11-20)
MAX_EMPTY_JOBS = 1
GATES = ("shape", "ask", "link", "quote", "repeat", "checker")


class ExamJob(BaseModel):
    """One writing job: a topic and its paper, run as a dry run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    topic: str = Field(min_length=1)
    source: str = Field(min_length=1)
    primer_pages: tuple[int, int] | None = None
    pages: tuple[int, int] | None = None
    asks: list[str] | None = None
    n: int = Field(default=4, ge=1, le=20)
    holdout: bool = False
    why: str

    @field_validator("why")
    @classmethod
    def _why_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("why must say why this job is in the exam")
        return value

    @field_validator("asks")
    @classmethod
    def _known_asks(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and (not value or any(a not in ASKS for a in value)):
            raise ValueError(f"asks must be some of {list(ASKS)}, not {value}")
        return value

    @model_validator(mode="after")
    def _page_ranges(self) -> "ExamJob":
        for name in ("primer_pages", "pages"):
            span = getattr(self, name)
            if span is not None and not 1 <= span[0] <= span[1]:
                raise ValueError(
                    f"{name} must be [first, last] with 1 <= first <= last"
                )
        return self


class JobScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    holdout: bool
    drafted: int = 0
    kept: int = 0
    dropped: dict[str, int] = Field(default_factory=lambda: dict.fromkeys(GATES, 0))
    niche: int = 0
    checker_errors: int = 0
    drops: list[Drop] = Field(default_factory=list)
    error: str = ""


class WriterExamReport(BaseModel):
    """The writer's score over the jobs, and whether it meets the bar."""

    model_config = ConfigDict(frozen=True)

    jobs: list[JobScore]
    drafted: int
    kept: int
    dropped: dict[str, int]
    niche: int
    checker_errors: int
    empty_jobs: int
    errors: int
    model: str = ""
    prompt_version: str = PROMPT_VERSION
    checker_prompt_version: str = CHECKER_PROMPT_VERSION

    @computed_field  # in model_dump(), so a saved report keeps its verdict
    @property
    def passed(self) -> bool:
        return (
            len(self.jobs) > 0
            and self.errors == 0
            and self.checker_errors == 0
            and self.drafted > 0
            and self.kept >= self.drafted * MIN_KEPT_SHARE
            and self.empty_jobs <= MAX_EMPTY_JOBS
            and self.dropped.get("quote", 0) == 0
        )


def load_jobs(path: Path = JOBS_FILE) -> list[ExamJob]:
    """Read the jobs file; any bad line is a ValueError naming the line."""
    jobs: list[ExamJob] = []
    seen: set[str] = set()
    for number, line in enumerate(Path(path).read_text("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            job = ExamJob.model_validate_json(line, strict=True)  # no type coercion
        except ValidationError as err:
            first = str(err).splitlines()[0]
            raise ValueError(f"{Path(path).name} line {number}: {first}") from err
        if job.id in seen:
            raise ValueError(f"{Path(path).name} line {number}: repeated id {job.id!r}")
        seen.add(job.id)
        jobs.append(job)
    if not jobs:
        raise ValueError(f"{Path(path).name} has no jobs")
    return jobs


def _primer_text(job: ExamJob, primer: list[str] | None) -> str:
    """The job's primer pages as write-cards builds them; ValueError if unusable."""
    if job.primer_pages is None:
        return ""
    if primer is None:
        raise ValueError("no primer: this job needs primer pages")
    first, last = job.primer_pages
    if last > len(primer):
        raise ValueError(f"the primer has {len(primer)} pages, not {last}")
    chosen = range(first, last + 1)
    if not any(primer[k - 1].strip() for k in chosen):
        raise ValueError(f"primer pages {first}-{last} have no text")
    return "\n\n".join(f"[primer page {k}]\n{primer[k - 1]}" for k in chosen)


def _score_job(
    job: ExamJob,
    write: Callable[..., object],
    check: Callable[[LongevityCard], CardVerdict],
    primer: list[str] | None,
    model: str,
) -> JobScore:
    niche = 0

    def counting_check(card: LongevityCard) -> CardVerdict:
        nonlocal niche
        verdict = check(card)
        if not verdict.ok and 4 in verdict.rules:
            niche += 1
        return verdict

    try:
        primer_text = _primer_text(job, primer)
        result = write(
            job.topic,
            job.source,
            n=job.n,
            model=model,
            check=counting_check,
            pages=job.pages,
            primer_text=primer_text,
            only_asks=job.asks,
            taken_ids=set(),
            taken_questions=set(),
        )
        r = result.report  # inside the try: an odd result fails only this job
        return JobScore(
            id=job.id,
            holdout=job.holdout,
            drafted=r.drafted,
            kept=r.kept,
            dropped={
                "shape": r.dropped_shape,
                "ask": r.dropped_ask,
                "link": r.dropped_link,
                "quote": r.dropped_quote,
                "repeat": r.dropped_repeat,
                "checker": r.dropped_checker,
            },
            niche=niche,
            checker_errors=r.checker_errors,
            drops=list(result.drops),
        )
    except Exception as err:  # noqa: BLE001 (one odd failure mustn't lose a paid run)
        lines = [line.strip() for line in str(err).splitlines() if line.strip()]
        reason = lines[0] if lines else type(err).__name__
        return JobScore(id=job.id, holdout=job.holdout, error=reason)


def _cut(text: str, limit: int) -> str:
    text = " ".join(text.split())  # one drop, one line
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _drop_lines(score: JobScore) -> list[str]:
    """One indented line per dropped draft: what we read to see why the writer fails."""
    return [
        f"  ✗ {d.gate}: {_cut(d.question, 100)} ({_cut(d.reason, 200)})"
        for d in score.drops
    ]


def _line(score: JobScore) -> str:
    if score.error:
        return f"{score.id}: error: {score.error}"
    d = score.dropped
    return (
        f"{score.id}: kept {score.kept}/{score.drafted}; dropped quote {d['quote']}, "
        f"checker {d['checker']} (niche {score.niche}), repeat {d['repeat']}, "
        f"shape {d['shape']}, ask {d['ask']}, link {d['link']}"
        + (f"; checker errors {score.checker_errors}" if score.checker_errors else "")
    )


def run_writer_exam(
    jobs: list[ExamJob],
    write: Callable[..., object] = write_cards,
    check: Callable[[LongevityCard], CardVerdict] = check_card,
    primer: list[str] | None = None,
    show: Callable[[str], None] = print,
    model: str = "sonnet",
) -> WriterExamReport:
    """Run every job once (a dry run: nothing is saved), print a line each, score."""
    scores: list[JobScore] = []
    for job in jobs:
        score = _score_job(job, write, check, primer, model)
        show(_line(score))
        for line in _drop_lines(score):
            show(line)
        scores.append(score)
    return WriterExamReport(
        jobs=scores,
        drafted=sum(s.drafted for s in scores),
        kept=sum(s.kept for s in scores),
        dropped={g: sum(s.dropped[g] for s in scores) for g in GATES},
        niche=sum(s.niche for s in scores),
        checker_errors=sum(s.checker_errors for s in scores),
        empty_jobs=sum(1 for s in scores if s.kept == 0),
        errors=sum(1 for s in scores if s.error),
        model=model,
    )
