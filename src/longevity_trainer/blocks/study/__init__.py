"""study: Deal the cards to study (due first, then new) by topic group, save each answer and its Leitner box, and summarise progress per group.

See SPEC.md in this folder (ADR 0003).
"""

from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from longevity_trainer.blocks.card_bank import LongevityCard
from quizkit.blocks.base import BlockSpec
from quizkit.blocks.deck_builder import build_deck
from quizkit.blocks.engine import Attempt
from quizkit.blocks.progress_store import ProgressFileError, ProgressStore
from quizkit.modes import Mode
from quizkit.progress import save_attempt, skill_stats

BLOCK_SPEC = BlockSpec(
    name="study",
    kind="script",
    goal="Deal the cards to study (due first, then new) by topic group, save each answer and its Leitner box, and summarise progress per group.",
    inputs=["cards", "n", "topic", "schedule", "now", "seed", "practise", "store"],
    outputs=[
        "SKILL",
        "group_of",
        "groups",
        "deal",
        "next_due",
        "schedule",
        "Saver",
        "stats_lines",
    ],
)

SKILL = "recall"  # every card asks you to recall a fact: one Leitner box per card
_DEAL_MODE = Mode(name="recall", show=["question"], skill=SKILL)  # only the order
MOST_MISSED = 5


def _now() -> datetime:
    return datetime.now(UTC)


def _check_aware(now: datetime) -> None:
    if now.utcoffset() is None:
        raise ValueError("now must have a timezone (e.g. datetime.now(UTC))")


Topics = str | Sequence[str] | None  # one text, several (match any), or all


def group_of(topic: str) -> str:
    """'hallmarks: dysbiosis' -> 'hallmarks'; a topic without ':' is its own group."""
    return topic.split(":", 1)[0].strip()


def deal(
    cards: list[LongevityCard],
    n: int,
    topic: Topics = None,
    schedule: dict[str, datetime] | None = None,
    now: datetime | None = None,
    seed: int | None = None,
    practise: bool = False,
) -> list[LongevityCard]:
    """Up to `n` cards: due first (most overdue first), then new. Cards not due yet
    only with `practise` (answering one early would move it up a box early)."""
    if n < 1:
        raise ValueError(f"n must be at least 1, not {n}")
    if now is not None:
        _check_aware(now)
    cards = _matching(cards, topic)
    if schedule is not None:
        now = now or _now()
        if not practise:
            cards = [c for c in cards if c.id not in schedule or schedule[c.id] <= now]
    if not cards:
        return []
    by_id = {c.id: c for c in cards}
    questions = build_deck(
        [c.to_quizkit() for c in cards],
        _DEAL_MODE,
        n,
        seed=seed,
        schedule=schedule,
        now=now,
    )
    return [by_id[q.card_id] for q in questions]


def _matching(cards: list[LongevityCard], topic: Topics) -> list[LongevityCard]:
    texts = [topic] if isinstance(topic, str) else list(topic or ())
    texts = [t.lower() for t in texts if t]  # blank texts are ignored
    if not texts:
        return list(cards)
    return [c for c in cards if any(t in c.topic.lower() for t in texts)]


def next_due(
    cards: list[LongevityCard], schedule: dict[str, datetime], topic: Topics = None
) -> datetime | None:
    """The soonest due time among the matching cards in the schedule."""
    times = [schedule[c.id] for c in _matching(cards, topic) if c.id in schedule]
    return min(times, default=None)


def groups(cards: list[LongevityCard]) -> list[str]:
    """The distinct topic groups, sorted."""
    return sorted({group_of(c.topic) for c in cards})


def schedule(store: ProgressStore) -> dict[str, datetime]:
    """When each answered card is next due."""
    return {card_id: box.due for card_id, box in store.boxes(SKILL).items()}


class Saver:
    """Saves each finally-marked answer and the card's new box; never raises on a
    progress-file problem: it warns once and tries again on the next answer (a busy
    file is often free a moment later), so the quiz goes on."""

    def __init__(
        self,
        store: ProgressStore,
        now: Callable[[], datetime] = _now,
        warn: Callable[[str], None] = print,
    ) -> None:
        self.store = store
        self.now = now
        self.warn = warn
        self.saved = 0
        self.unsaved = 0

    def __call__(self, attempt: Attempt) -> None:
        try:
            save_attempt(self.store, attempt, SKILL, self.now())
        except ProgressFileError as err:
            self.unsaved += 1
            if self.unsaved == 1:
                self.warn(
                    f"progress not saved: {err}. "
                    "The quiz goes on; later answers are still tried."
                )
            return
        self.saved += 1


def _boxes(by_box: dict[int, int]) -> list[str]:
    return [f"box {box}: {count}" for box, count in by_box.items()]


def stats_lines(
    cards: list[LongevityCard], store: ProgressStore | None, now: datetime
) -> list[str]:
    """The stats screen: per group, then all cards, the last 7 days, most missed."""
    _check_aware(now)
    groups: dict[str, list[LongevityCard]] = {}
    for c in cards:
        groups.setdefault(group_of(c.topic), []).append(c)
    if store is None:
        lines = [f"{len(cards)} cards, all new (no progress saved yet):"]
        lines += [f"  {g}: {len(group)} cards" for g, group in sorted(groups.items())]
        return lines

    def summary(ids: list[str], top: int = MOST_MISSED):
        s = skill_stats(store, ids, SKILL, now, top=top)
        parts = [
            f"{s.cards} cards",
            f"new {s.new}",
            *_boxes(s.by_box),
            f"due now: {s.due}",
        ]
        return s, " · ".join(parts)

    lines = [
        f"  {g}: {summary([c.id for c in group])[1]}"
        for g, group in sorted(groups.items())
    ]
    every, line = summary([c.id for c in cards])
    lines.append(f"All: {line}")
    lines.append(f"Last 7 days: {every.recent_right} / {every.recent_answered} right")
    by_id = {c.id: c for c in cards}  # most_missed only has these cards' ids
    if every.most_missed:
        lines.append("Most missed:")
        lines += [f"{times}× {by_id[cid].question}" for cid, times in every.most_missed]
    return lines
