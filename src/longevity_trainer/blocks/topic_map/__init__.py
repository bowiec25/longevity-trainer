"""topic_map: Sort the cards onto broad shelves: map each card's topic to its topic-map entry and that entry's area (How we age, Drugs & treatments, ...)

See SPEC.md in this folder (ADR 0003).
"""

import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from longevity_trainer.blocks.card_bank import ROOT, LongevityCard
from longevity_trainer.blocks.study import group_of
from quizkit.blocks.base import BlockSpec

BLOCK_SPEC = BlockSpec(
    name="topic_map",
    kind="script",
    goal="Sort the cards onto broad shelves: map each card's topic to its topic-map entry and that entry's area (How we age, Drugs & treatments, ...)",
    inputs=["path", "card_topic", "topics", "cards", "topic_id"],
    outputs=[
        "TOPICS_FILE",
        "AREAS",
        "Topic",
        "load_topic_map",
        "area_of",
        "areas_in",
        "coverage_lines",
        "misfiled",
    ],
)

TOPICS_FILE = ROOT / "data" / "topics.jsonl"
AREAS = (
    "How we age",
    "Big ideas",
    "Drugs & treatments",
    "Supplements",
    "Lifestyle",
    "Measuring ageing",
    "Evidence & trials",
    "Industry",
)


def _slug(text: str) -> str:
    """card_writer.slug's rule, kept here so the quiz doesn't import the writer
    (Claude, downloads) for one line: 'NAD+ boosters' -> 'nad-boosters'."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class Topic(BaseModel):
    """One line of the topic map (other keys, like `primer` and `kinds`, ignored)."""

    model_config = ConfigDict(frozen=True, extra="ignore", strict=True)

    id: str
    topic: str
    group: str
    area: str
    status: str
    aliases: list[str] = []
    parts: list[str] = []  # e.g. the 12 hallmarks: cards filed '<group>: <part>'


def load_topic_map(path: Path | None = None) -> list[Topic]:
    """Every topic-map line, in file order (default file: TOPICS_FILE, read now)."""
    path = TOPICS_FILE if path is None else Path(path)
    topics: list[Topic] = []
    names: set[str] = set()  # ids and aliases: each must lead to one topic
    for number, line in enumerate(path.read_text("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as err:
            raise ValueError(f"{path} line {number}: not JSON ({err})") from err
        try:  # a list or string line fails here too ("bad line")
            topic = Topic.model_validate(row)
        except ValidationError as err:
            where = ".".join(str(p) for p in err.errors()[0]["loc"])
            raise ValueError(f"{path} line {number}: bad {where or 'line'}") from err
        if topic.area not in AREAS:
            raise ValueError(f"{path} line {number}: unknown area {topic.area!r}")
        part_slugs = [_slug(part) for part in topic.parts]
        if len(set(part_slugs)) != len(part_slugs):
            raise ValueError(f"{path} line {number}: a part is listed twice")
        if "" in part_slugs:
            raise ValueError(f"{path} line {number}: a part is blank")
        for name in [topic.id, *topic.aliases]:
            if name in names:
                raise ValueError(f"{path} line {number}: {name!r} is used twice")
            names.add(name)
        topics.append(topic)
    return topics


def _find(name: str, topics: list[Topic]) -> Topic | None:
    """The topic-map entry a name finds once slugged, by id or alias."""
    key = _slug(name)
    return next((t for t in topics if key == t.id or key in t.aliases), None)


def _entry(card_topic: str, topics: list[Topic]) -> Topic | None:
    """The topic-map entry a card topic's group finds."""
    return _find(group_of(card_topic), topics)


def area_of(card_topic: str, topics: list[Topic]) -> str | None:
    """A card's shelf, from its topic's group (by id or alias); None if unknown."""
    topic = _entry(card_topic, topics)
    return topic.area if topic else None


def _part_of(card: LongevityCard, topics: list[Topic]) -> tuple[Topic, str] | None:
    """(the topic with parts, the text after ':') for a card filed on a part."""
    _, colon, text = card.topic.partition(":")
    topic = _entry(card.topic, topics)
    if not colon or topic is None or not topic.parts:
        return None
    return topic, text.strip()


def coverage_lines(
    cards: list[LongevityCard], topics: list[Topic], topic_id: str
) -> list[str]:
    """Per part: easy what / how cards and hard cards; the gaps to write next."""
    topic = _find(topic_id, topics)
    if topic is None or not topic.parts:
        with_parts = ", ".join(t.id for t in topics if t.parts) or "none"
        raise ValueError(f"no parts for {topic_id!r}. Topics with parts: {with_parts}")
    on_part: dict[str, list[LongevityCard]] = {_slug(p): [] for p in topic.parts}
    for card in cards:
        found = _part_of(card, topics)
        if found and found[0] is topic:
            on_part.get(_slug(found[1]), []).append(card)
    rows, covered = [], 0
    for part in topic.parts:
        here = on_part[_slug(part)]
        easy = [c for c in here if c.difficulty == "easy"]
        what = sum(c.kind in ("name", "term", "fact") for c in easy)
        how = sum(c.kind == "explain" for c in easy)
        needs = [n for n, ok in (("easy what", what), ("easy how", how)) if not ok]
        covered += not needs
        end = f" (needs: {', '.join(needs)})" if needs else " ✓"
        rows.append(
            f"  {part}: easy {what} what, {how} how; {len(here) - len(easy)} hard{end}"
        )
    head = (
        f"{topic.id}: {covered} of {len(topic.parts)} parts covered in easy mode"
        " (each needs an easy what and how card)"
    )
    return [head, *rows]


def misfiled(cards: list[LongevityCard], topics: list[Topic]) -> list[str]:
    """Cards filed '<group>: <x>' under a topic with parts, where x isn't a part."""
    problems = []
    for card in cards:
        found = _part_of(card, topics)
        if found is None:
            continue
        topic, text = found
        if _slug(text) not in {_slug(p) for p in topic.parts}:
            problems.append(f"{card.id}: '{text}' isn't one of {topic.id}'s parts")
    return problems


def areas_in(cards: list[LongevityCard], topics: list[Topic]) -> list[str]:
    """The shelves holding at least one of the cards, in AREAS order."""
    found = {area_of(card.topic, topics) for card in cards}
    return [area for area in AREAS if area in found]
