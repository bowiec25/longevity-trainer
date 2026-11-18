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
        "CHAPTERS",
        "syllabus_lines",
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

# The primer's chapters, in our own short words (never the primer's text).
CHAPTERS = {
    0: "How to read the evidence",
    1: "What ageing is",
    2: "Hallmarks and pathways",
    3: "Big ideas",
    4: "Judging the evidence",
    5: "Consumer longevity",
    6: "Drugs",
    7: "Peptides",
    8: "Hormones",
    9: "Supplements",
    10: "Procedures and lifestyle",
    11: "Blood tests",
    12: "Ageing clocks",
    13: "Scans",
    14: "Wearables",
    15: "Glucose and genes",
    16: "Health data",
    17: "The drug pipeline",
    18: "Landmark trials",
    19: "Regulators",
    20: "Money and deals",
    21: "What changed",
    22: "Where the news is",
    23: "People, events and books",
}
WHAT_KINDS = ("name", "term", "fact")
KINDS = (*WHAT_KINDS, "explain", "grade")


def _slug(text: str) -> str:
    """card_writer.slug's rule, kept here so the quiz doesn't import the writer
    (Claude, downloads) for one line: 'NAD+ boosters' -> 'nad-boosters'."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


class Topic(BaseModel):
    """One line of the topic map (other keys ignored)."""

    model_config = ConfigDict(frozen=True, extra="ignore", strict=True)

    id: str
    topic: str
    group: str
    area: str
    status: str
    aliases: list[str] = []
    parts: list[str] = []  # e.g. the 12 hallmarks: cards filed '<group>: <part>'
    primer: str = ""  # its primer section, e.g. "2.1" or "11.4-11.5"
    kinds: list[str] = []  # the card kinds it should have


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
        for kind in topic.kinds:
            if kind not in KINDS:
                raise ValueError(f"{path} line {number}: unknown kind {kind!r}")
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
    rows = _part_rows(cards, topics, topic)
    covered = sum(ok for _, ok in rows)
    head = (
        f"{topic.id}: {covered} of {len(topic.parts)} parts covered in easy mode"
        " (each needs an easy what and how card)"
    )
    return [head, *(line for line, _ in rows)]


def _part_rows(
    cards: list[LongevityCard], topics: list[Topic], topic: Topic
) -> list[tuple[str, bool]]:
    """(line, covered) for each of a topic's parts, in the topic's order."""
    on_part: dict[str, list[LongevityCard]] = {_slug(p): [] for p in topic.parts}
    for card in cards:
        found = _part_of(card, topics)
        if found and found[0] is topic:
            on_part.get(_slug(found[1]), []).append(card)
    return [
        _count_line(part, on_part[_slug(part)], ["what", "how"]) for part in topic.parts
    ]


def _count_line(
    name: str, cards: list[LongevityCard], wanted: list[str]
) -> tuple[str, bool]:
    """'  <name>: easy w what, h how; x hard' + ' ✓' or the missing easy cards."""
    easy = [c for c in cards if c.difficulty == "easy"]
    what = sum(c.kind in WHAT_KINDS for c in easy)
    how = sum(c.kind == "explain" for c in easy)
    have = {"what": what, "how": how, "any": len(easy)}
    label = {"what": "easy what", "how": "easy how", "any": "an easy card"}
    needs = [label[w] for w in wanted if not have[w]]
    end = f" (needs: {', '.join(needs)})" if needs else " ✓"
    hard = len(cards) - len(easy)
    return f"  {name}: easy {what} what, {how} how; {hard} hard{end}", not needs


def _wanted(topic: Topic) -> list[str]:
    """The easy cards a topic's kinds call for: what, how, or else any one."""
    wanted = []
    if any(k in WHAT_KINDS for k in topic.kinds):
        wanted.append("what")
    if "explain" in topic.kinds:
        wanted.append("how")
    return wanted or ["any"]


def _chapter(topic: Topic) -> int | None:
    """The whole number the primer section starts with ('11.4-11.5' -> 11)."""
    digits = re.match(r"\d+", topic.primer)
    return int(digits.group()) if digits else None


def syllabus_lines(cards: list[LongevityCard], topics: list[Topic]) -> list[str]:
    """Every learnable sub-topic, chapter by chapter: easy / hard cards, gaps."""
    learn = [t for t in topics if t.status == "v1"]
    mine: dict[str, list[LongevityCard]] = {t.id: [] for t in learn}
    for card in cards:
        topic = _entry(card.topic, topics)
        if topic is not None and topic.id in mine:
            mine[topic.id].append(card)
    chapters: dict[int | None, list[tuple[str, bool]]] = {}
    for topic in learn:
        if topic.parts:
            parts = _part_rows(cards, topics, topic)
            done = sum(ok for _, ok in parts)
            ok = done == len(parts)
            line = (
                f"  {topic.id}: {done} of {len(parts)} parts covered"
                f" (see: coverage {topic.id}){' ✓' if ok else ''}"
            )
        else:
            line, ok = _count_line(topic.id, mine[topic.id], _wanted(topic))
        chapters.setdefault(_chapter(topic), []).append((line, ok))
    order = sorted(k for k in chapters if k is not None)
    if None in chapters:
        order.append(None)
    covered = sum(ok for rows in chapters.values() for _, ok in rows)
    lines = [f"Syllabus: {covered} of {len(learn)} sub-topics covered in easy mode"]
    for number in order:
        rows = chapters[number]
        done = sum(ok for _, ok in rows)
        if number is None:
            head = "?? no chapter"
        else:
            head = f"{number:02d} {CHAPTERS.get(number, f'chapter {number}')}"
        lines.append(f"{head}: {done} of {len(rows)} covered")
        lines.extend(line for line, _ in rows)
    status = [t.status for t in topics if t.status != "v1"]
    later, read = status.count("after-m5"), status.count("read")
    lines.append(f"Later (dated facts, wait for M5): {later} sub-topics")
    lines.append(f"Read, don't quiz: {read} sub-topics")
    if other := len(status) - later - read:
        lines.append(f"Other status: {other} sub-topics")
    return lines


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
