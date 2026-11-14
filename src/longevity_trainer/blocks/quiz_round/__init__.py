"""quiz_round: Run one quiz round for any screen: set it up (deal, progress, judge), mark each answer, and say what to show after it (verdict, model answer, receipt)

See SPEC.md in this folder (ADR 0003, ADR 0009).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from longevity_trainer.blocks.card_bank import ROOT, LongevityCard, load_cards
from longevity_trainer.blocks.marking import make_judge as default_make_judge
from longevity_trainer.blocks.study import Saver, deal, groups, next_due, schedule
from quizkit.blocks.base import BlockSpec
from quizkit.blocks.engine import Attempt, QuizResult, QuizSession
from quizkit.blocks.progress_store import ProgressFileError, ProgressStore
from quizkit.blocks.receipts import Receipt
from quizkit.models import Judge, Verdict

BLOCK_SPEC = BlockSpec(
    name="quiz_round",
    kind="script",
    goal="Run one quiz round for any screen: set it up (deal, progress, judge), mark each answer, and say what to show after it (verdict, model answer, receipt)",
    inputs=[
        "options",
        "files",
        "bank",
        "now",
        "make_judge",
        "before_asking",
        "warn",
        "practise_hint",
        "clock",
    ],
    outputs=[
        "RoundOptions",
        "RoundFiles",
        "PROGRESS_FILE",
        "JUDGE_CACHE",
        "setup",
        "SetupProblem",
        "SELF_YES",
        "SELF_NO",
        "OWN_MARK_QUESTION",
        "feedback",
        "own_mark_line",
        "NOT_THIS_TIME",
        "receipt_line",
        "score_line",
        "QuizScreen",
    ],
)

PROGRESS_FILE = ROOT / "data" / "progress.db"  # gitignored: your own progress
JUDGE_CACHE = ROOT / "data" / "judge_cache.jsonl"  # gitignored: your answers

SELF_YES = Verdict(correct=True, reason="you marked it right", source="self")
SELF_NO = Verdict(correct=False, reason="you marked it wrong", source="self")
OWN_MARK_QUESTION = "Count it as right?"
NOT_THIS_TIME = "✗ Not this time"
WEB_PRACTISE_HINT = "turn on Practise"


# --- settings ----------------------------------------------------------------------


@dataclass(frozen=True)
class RoundOptions:
    """What kind of round: which topic, how many, practise, Claude, saving."""

    topic: str | tuple[str, ...] | None = None  # several: cards matching any
    n: int = 10
    practise: bool = False
    judge: bool = True
    save: bool = True
    seed: int | None = None

    def __post_init__(self) -> None:
        if self.n < 1:
            raise ValueError(f"n must be at least 1, not {self.n}")


def _progress_default() -> Path:
    return PROGRESS_FILE  # read when built, so tests can point it elsewhere


def _cache_default() -> Path:
    return JUDGE_CACHE


@dataclass(frozen=True)
class RoundFiles:
    """Where progress and Claude's verdicts are saved."""

    progress: Path = field(default_factory=_progress_default)
    judge_cache: Path = field(default_factory=_cache_default)


# --- setting up --------------------------------------------------------------------


class SetupProblem(Exception):
    """Why no quiz starts: lines to show; nothing_due = "come back later" (not an
    error)."""

    def __init__(self, lines: list[str], nothing_due: bool = False) -> None:
        super().__init__("\n".join(lines))
        self.lines = list(lines)
        self.nothing_due = nothing_due


@dataclass(frozen=True)
class Round:
    """A round ready to play: the cards in order, the judge, and the saver."""

    cards: list[LongevityCard]
    judge: Judge | None
    saver: Saver | None


def _now() -> datetime:
    return datetime.now(UTC)


def _open(path: Path) -> ProgressStore:
    try:
        return ProgressStore(path)
    except ProgressFileError as err:
        raise SetupProblem([f"can't use {path.name}: {err}"]) from err


def setup(
    options: RoundOptions,
    files: RoundFiles | None = None,
    bank: list[LongevityCard] | None = None,
    now: datetime | None = None,
    make_judge: Callable[..., Judge] = default_make_judge,
    before_asking: Callable[[], None] | None = None,
    warn: Callable[[str], None] = print,
    practise_hint: str = "--practise",
    clock: Callable[[], datetime] | None = None,
) -> Round:
    """Deal a round (due, then new) and get its judge and saver ready."""
    files = files or RoundFiles()
    bank = load_cards() if bank is None else bank
    now = now or _now()
    saving = options.save and not options.practise
    store = None
    plan = None  # no progress yet: every card is new
    if files.progress.exists():
        store = _open(files.progress)
        try:
            plan = schedule(store)
        except ProgressFileError as err:
            raise SetupProblem([f"can't read {files.progress.name}: {err}"]) from err
    cards = deal(
        bank,
        options.n,
        topic=options.topic,
        schedule=plan,
        now=now,
        seed=options.seed,
        practise=options.practise,
    )
    if not cards:
        soonest = next_due(bank, plan or {}, topic=options.topic)
        if soonest is not None:
            when = soonest.astimezone().strftime("%a %d %b %H:%M")
            raise SetupProblem(
                [
                    f"Nothing due. Next card due {when}. ({practise_hint} to review anyway)"
                ],
                nothing_due=True,
            )
        topics = [options.topic] if isinstance(options.topic, str) else options.topic
        wanted = [t for t in topics or () if t]  # blanks are ignored, as in study
        if wanted:
            names = " or ".join(repr(t) for t in wanted)
            raise SetupProblem(
                [f"no cards on a topic containing {names}. Topics:"]
                + [f"  {group}" for group in groups(bank)]
            )
        raise SetupProblem(["no cards in the bank"])
    saver = None
    if saving:
        if store is None:  # created only now that a quiz starts
            store = _open(files.progress)
        saver = Saver(store, now=clock or _now, warn=warn)
    judge = None
    if options.judge:
        judge = make_judge(cache_file=files.judge_cache, before_asking=before_asking)
    return Round(cards=cards, judge=judge, saver=saver)


# --- what to say -------------------------------------------------------------------


def feedback(attempt: Attempt, card: LongevityCard) -> list[str]:
    """What to say right after an answer, before any own mark."""
    verdict = attempt.verdict
    checked = verdict is not None and verdict.source != "not_checked"
    if attempt.correct:
        if checked:
            return [
                f"✓ Right (Claude: {verdict.reason})",
                f"Model answer: {card.answers[0]}",
            ]
        return ["✓ Right"]
    lines = []
    if checked:
        lines.append(f"✗ Claude: {verdict.reason}")
    elif verdict is not None:  # Claude was asked but couldn't check
        lines.append(f"(Claude: {verdict.reason})")
    lines.append(f"Answer: {card.answers[0]}")
    return lines


def own_mark_line(got_it: bool) -> str:
    return "✓ Counted" if got_it else NOT_THIS_TIME


def receipt_line(card: LongevityCard) -> str:
    r = card.receipt
    return f'Receipt: "{r.quote}" ({r.source}, p. {r.page})'


def score_line(result: QuizResult) -> str:
    return f"Score: {result.correct} / {result.answered}"


# --- the quiz for a screen that redraws on every click -----------------------------

Phase = Literal["setup", "asking", "own_mark", "result", "ended"]


@dataclass(frozen=True)
class QuestionView:
    card_id: str
    number: int  # 1-based
    total: int
    question: str
    topic: str


@dataclass(frozen=True)
class MarkView:
    card_id: str
    typed: str
    lines: list[str]
    question: str = OWN_MARK_QUESTION


@dataclass(frozen=True)
class ResultView:
    card_id: str
    typed: str
    right: bool
    lines: list[str]
    receipt: Receipt
    warning: str | None = None


@dataclass
class QuizScreen:
    """One quiz in one browser tab, kept between reruns of the page. Only the click
    methods move it on; the page just draws `view` / `marking` / `result` /
    `summary` / `problems`."""

    files: RoundFiles = field(default_factory=RoundFiles)
    bank: list[LongevityCard] | None = None
    make_judge: Callable[..., Judge] = default_make_judge
    now: Callable[[], datetime] = _now
    phase: Phase = "setup"
    problems: list[str] = field(default_factory=list)
    nothing_due: bool = False
    view: QuestionView | None = None
    marking: MarkView | None = None
    result: ResultView | None = None
    summary: list[str] = field(default_factory=list)
    _options: RoundOptions | None = field(default=None, init=False)
    _session: QuizSession | None = field(default=None, init=False)
    _saver: Saver | None = field(default=None, init=False)
    _cards: dict[str, LongevityCard] = field(default_factory=dict, init=False)
    _warnings: list[str] = field(default_factory=list, init=False)

    # --- clicks -------------------------------------------------------------------

    def start(self, options: RoundOptions) -> None:
        """Start a round (Start button); a setup problem goes to `problems`."""
        if self.phase not in ("setup", "ended"):
            return
        self._reset()
        try:
            round_ = setup(
                options,
                self.files,
                bank=self.bank,
                now=self.now(),
                make_judge=self.make_judge,
                before_asking=None,
                warn=self._warnings.append,
                practise_hint=WEB_PRACTISE_HINT,
                clock=self.now,
            )
        except SetupProblem as problem:
            self.problems, self.nothing_due = problem.lines, problem.nothing_due
            self.phase = "setup"
            return
        self._options = options
        self._saver = round_.saver
        self._cards = {c.id: c for c in round_.cards}
        self._session = QuizSession(
            [c.to_question() for c in round_.cards], judge=round_.judge
        )
        self._advance()

    def submit(self, typed: str, card_id: str) -> None:
        """Check an answer for the question `card_id`."""
        if self.phase != "asking" or self.view is None or card_id != self.view.card_id:
            return
        session = self._quiz
        attempt = session.answer(typed)
        card = self._cards[card_id]
        lines = feedback(attempt, card)
        if session.can_own_mark:  # wrong, typed, and nobody could check it
            self.marking = MarkView(card_id=card_id, typed=typed, lines=lines)
            self.phase = "own_mark"
            return
        if not attempt.correct:
            lines.append(NOT_THIS_TIME)
        self._final(attempt, lines)

    def mark(self, got_it: bool, card_id: str) -> None:
        """Your own mark (Yes / No) on the answer waiting for it."""
        if self.phase != "own_mark" or self.marking is None:
            return
        if card_id != self.marking.card_id:
            return
        lines = [*self.marking.lines, own_mark_line(got_it)]
        attempt = self._quiz.own_mark(SELF_YES if got_it else SELF_NO, card_id=card_id)
        self._final(attempt, lines)

    def next(self, card_id: str) -> None:
        """Go on from the result of `card_id` (Next button)."""
        if self.phase != "result" or self.result is None:
            return
        if card_id != self.result.card_id:
            return
        self._advance()

    def stop(self) -> None:
        """Stop now: the score so far. An answer waiting for your mark isn't saved."""
        if self.phase not in ("asking", "own_mark", "result"):
            return
        self._finish()

    def new_quiz(self) -> None:
        """Back to the settings, after a round has ended."""
        if self.phase == "ended":
            self._reset()
            self.phase = "setup"

    # --- inside ---------------------------------------------------------------------

    @property
    def _quiz(self) -> QuizSession:
        assert self._session is not None, "no quiz running"
        return self._session

    def _reset(self) -> None:
        self.problems, self.summary, self._warnings = [], [], []
        self.nothing_due = False
        self.view = self.marking = self.result = None
        self._options = self._session = self._saver = None
        self._cards = {}

    def _advance(self) -> None:
        session = self._quiz
        self.marking = self.result = None
        question = session.current
        if question is None:
            self._finish()
            return
        done = session.result()
        card = self._cards[question.card_id]
        self.view = QuestionView(
            card_id=card.id,
            number=done.answered + done.skipped + 1,
            total=done.total,
            question=card.question,
            topic=card.topic,
        )
        self.phase = "asking"

    def _final(self, attempt: Attempt, lines: list[str]) -> None:
        """An answer is final: save it first, then show it."""
        warning = None
        if self._saver is not None:
            warned = len(self._warnings)  # the Saver warns on its first failure only
            self._saver(attempt)
            if len(self._warnings) > warned:
                warning = self._warnings[-1]
        card = self._cards[attempt.question.card_id]
        self.marking = None
        self.result = ResultView(
            card_id=card.id,
            typed=attempt.typed,
            right=attempt.correct,
            lines=lines,
            receipt=card.receipt,
            warning=warning,
        )
        self.phase = "result"

    def _finish(self) -> None:
        summary = [score_line(self._quiz.result())]
        if self._saver is not None:
            summary.append(f"{self._saver.saved} answers saved")
            if self._saver.unsaved:
                summary.append(f"{self._saver.unsaved} answers not saved")
        elif self._options is not None and self._options.practise:
            summary.append("Practise: nothing saved")
        self.summary = summary
        self.view = self.marking = self.result = None
        self.phase = "ended"
