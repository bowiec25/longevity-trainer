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
    inputs=["path", "card_topic", "topics", "cards"],
    outputs=["TOPICS_FILE", "AREAS", "Topic", "load_topic_map", "area_of", "areas_in"],
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
        for name in [topic.id, *topic.aliases]:
            if name in names:
                raise ValueError(f"{path} line {number}: {name!r} is used twice")
            names.add(name)
        topics.append(topic)
    return topics


def area_of(card_topic: str, topics: list[Topic]) -> str | None:
    """A card's shelf, from its topic's group (by id or alias); None if unknown."""
    key = _slug(group_of(card_topic))
    for topic in topics:
        if key == topic.id or key in topic.aliases:
            return topic.area
    return None


def areas_in(cards: list[LongevityCard], topics: list[Topic]) -> list[str]:
    """The shelves holding at least one of the cards, in AREAS order."""
    found = {area_of(card.topic, topics) for card in cards}
    return [area for area in AREAS if area in found]
