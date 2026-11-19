"""Tests for the topic_map block: its contract (ID card + SPEC.md) and its behaviour.

Written from SPEC.md "How to test", before the code. Names are reached through
`block.<name>` so the contract tests still run while the code isn't built. Small
topic files are written to tmp_path; the real-data tests read data/topics.jsonl
and the real card bank.
"""

import json
import re
from pathlib import Path

import pytest

import longevity_trainer.blocks.topic_map as block
from longevity_trainer.blocks.card_bank import ROOT, LongevityCard, load_cards
from quizkit.blocks.base import missing_spec_sections, spec_section
from quizkit.blocks.receipts import Receipt

SPEC_MD = Path(block.__file__).parent / "SPEC.md"
QUOTE = "A word-for-word quote that is long enough to count as a receipt."
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


# --- contract --------------------------------------------------------------------


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "topic_map"
    assert block.BLOCK_SPEC.kind == "script"


def test_spec_md_has_every_section():
    assert missing_spec_sections(SPEC_MD) == []


def test_inputs_and_outputs_match_spec():
    """The code's ID card (BLOCK_SPEC) and the job description (SPEC.md) agree."""
    for field, section in [("inputs", "Inputs"), ("outputs", "Outputs")]:
        listed = getattr(block.BLOCK_SPEC, field)
        text = spec_section(SPEC_MD, section)
        for item in listed:
            assert item in text, (
                f"BLOCK_SPEC.{field} has {item!r}, not in SPEC.md {section}"
            )
        if "TODO" not in text:  # once the SPEC section is filled in...
            assert listed, (
                f"SPEC.md {section} is filled in: copy it into BLOCK_SPEC.{field}"
            )


def test_block_spec_lists_every_spec_input_and_output():
    assert set(block.BLOCK_SPEC.inputs) == {
        "path",
        "card_topic",
        "topics",
        "cards",
        "topic_id",
    }
    assert set(block.BLOCK_SPEC.outputs) == {
        "TOPICS_FILE",
        "AREAS",
        "Topic",
        "load_topic_map",
        "area_of",
        "coverage_lines",
        "misfiled",
        "areas_in",
        "CHAPTERS",
        "syllabus_lines",
        "todo_lines",
    }


# --- helpers ---------------------------------------------------------------------


def row(id_, area="How we age", **extra):
    """A valid topic-map line: a v1 line gets priority "core" unless given."""
    line = {
        "id": id_,
        "topic": f"The topic {id_}",
        "group": "g",
        "area": area,
        "status": "v1",
    } | extra
    if line["status"] == "v1" and "priority" not in extra:
        line["priority"] = "core"
    return line


def write_lines(path, lines):
    """Each item: a dict (written as JSON) or a str (written as is)."""
    text = "\n".join(x if isinstance(x, str) else json.dumps(x) for x in lines)
    path.write_text(text + "\n", encoding="utf-8")
    return path


def topic(id_, area, aliases=(), parts=None):
    extra = {} if parts is None else {"parts": list(parts)}
    return block.Topic(
        id=id_,
        topic=f"The topic {id_}",
        group="g",
        area=area,
        status="v1",
        aliases=list(aliases),
        **extra,
    )


def small_map():
    return [
        topic("hallmarks", "How we age"),
        topic("rapamycin", "Drugs & treatments"),
        topic("nad-boosters", "Supplements"),
        topic("exercise", "Lifestyle", aliases=["physical-activity"]),
    ]


def make_card(card_id, topic_text, kind="name", difficulty=None):
    return LongevityCard(
        id=card_id,
        kind=kind,
        difficulty=difficulty,
        topic=topic_text,
        question=f"What is the answer to question {card_id}?",
        answers=["an answer"],
        receipt=Receipt(source="src-1", quote=QUOTE, page=3),
    )


# --- the constants ---------------------------------------------------------------


def test_topics_file_is_data_topics_jsonl():
    assert block.TOPICS_FILE == ROOT / "data" / "topics.jsonl"


def test_areas_are_the_shelves_in_page_order():
    assert block.AREAS == AREAS


# --- load_topic_map ----------------------------------------------------------------


def test_load_reads_every_line_in_order_all_statuses(tmp_path):
    path = write_lines(
        tmp_path / "t.jsonl",
        [
            row("b", status="v1"),
            row("a", area="Industry", status="later"),
            row("c", area="Lifestyle", status="read-only"),
        ],
    )
    topics = block.load_topic_map(path)
    assert [t.id for t in topics] == ["b", "a", "c"]
    assert [t.status for t in topics] == ["v1", "later", "read-only"]
    assert all(isinstance(t, block.Topic) for t in topics)
    first = topics[0]
    assert (first.topic, first.group, first.area) == ("The topic b", "g", "How we age")


def test_load_skips_blank_lines(tmp_path):
    path = write_lines(tmp_path / "t.jsonl", [row("a"), "", "   ", row("b")])
    assert [t.id for t in block.load_topic_map(path)] == ["a", "b"]


def test_aliases_default_to_empty_and_are_read(tmp_path):
    path = write_lines(
        tmp_path / "t.jsonl", [row("a"), row("b", aliases=["bee", "b-2"])]
    )
    a, b = block.load_topic_map(path)
    assert a.aliases == []
    assert b.aliases == ["bee", "b-2"]


def test_extra_keys_primer_and_kinds_are_accepted(tmp_path):
    path = write_lines(
        tmp_path / "t.jsonl", [row("a", primer="2.1", kinds=["name", "explain"])]
    )
    assert [t.id for t in block.load_topic_map(path)] == ["a"]


def test_primer_and_kinds_default_to_empty_and_are_read(tmp_path):
    path = write_lines(
        tmp_path / "t.jsonl",
        [row("a"), row("b", primer="11.4-11.5", kinds=["name", "explain"])],
    )
    a, b = block.load_topic_map(path)
    assert (a.primer, a.kinds) == ("", [])
    assert (b.primer, b.kinds) == ("11.4-11.5", ["name", "explain"])


def test_other_extra_keys_like_note_are_accepted(tmp_path):
    path = write_lines(tmp_path / "t.jsonl", [row("a", note="a free-text note")])
    assert [t.id for t in block.load_topic_map(path)] == ["a"]


def test_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        block.load_topic_map(tmp_path / "nope.jsonl")


def test_no_argument_follows_a_monkeypatched_topics_file(tmp_path, monkeypatch):
    path = write_lines(tmp_path / "t.jsonl", [row("only-one")])
    monkeypatch.setattr(block, "TOPICS_FILE", path)
    assert [t.id for t in block.load_topic_map()] == ["only-one"]


def test_no_argument_with_a_missing_patched_file_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(block, "TOPICS_FILE", tmp_path / "gone.jsonl")
    with pytest.raises(FileNotFoundError):
        block.load_topic_map()


@pytest.mark.parametrize(
    "bad",
    [
        "{not json",
        "[1, 2, 3]",
        '"just a string"',
        json.dumps({k: v for k, v in row("x").items() if k != "id"}),
        json.dumps({k: v for k, v in row("x").items() if k != "topic"}),
        json.dumps({k: v for k, v in row("x").items() if k != "group"}),
        json.dumps({k: v for k, v in row("x").items() if k != "area"}),
        json.dumps({k: v for k, v in row("x").items() if k != "status"}),
        json.dumps(row("x") | {"id": 7}),
        json.dumps(row("x") | {"topic": None}),
        json.dumps(row("x") | {"group": ["g"]}),
        json.dumps(row("x") | {"area": 3}),
        json.dumps(row("x") | {"status": True}),
        json.dumps(row("x") | {"primer": 2.1}),
        json.dumps(row("x") | {"kinds": "name"}),
    ],
    ids=[
        "not-json",
        "list",
        "string",
        "no-id",
        "no-topic",
        "no-group",
        "no-area",
        "no-status",
        "int-id",
        "null-topic",
        "list-group",
        "int-area",
        "bool-status",
        "float-primer",
        "string-kinds",
    ],
)
def test_a_bad_line_raises_value_error_naming_the_line(tmp_path, bad):
    path = write_lines(tmp_path / "t.jsonl", [row("a"), row("b"), bad])
    with pytest.raises(ValueError, match="line 3"):
        block.load_topic_map(path)


def test_an_unknown_area_raises_naming_line_and_area(tmp_path):
    path = write_lines(tmp_path / "t.jsonl", [row("a"), row("b", area="Gardening")])
    with pytest.raises(ValueError, match="line 2") as err:
        block.load_topic_map(path)
    assert "Gardening" in str(err.value)


def test_an_unknown_kind_raises_naming_line_and_kind(tmp_path):
    path = write_lines(
        tmp_path / "t.jsonl", [row("a"), row("b", kinds=["name", "explian"])]
    )
    with pytest.raises(ValueError, match="line 2") as err:
        block.load_topic_map(path)
    assert "explian" in str(err.value)


def test_every_known_kind_is_accepted(tmp_path):
    kinds = ["name", "term", "fact", "explain", "grade"]
    path = write_lines(tmp_path / "t.jsonl", [row("a", kinds=kinds)])
    assert block.load_topic_map(path)[0].kinds == kinds


def test_a_repeated_id_raises_naming_the_line(tmp_path):
    path = write_lines(tmp_path / "t.jsonl", [row("a"), row("b"), row("a")])
    with pytest.raises(ValueError, match="line 3"):
        block.load_topic_map(path)


def test_an_alias_equal_to_another_id_raises(tmp_path):
    path = write_lines(tmp_path / "t.jsonl", [row("a"), row("b", aliases=["a"])])
    with pytest.raises(ValueError, match="line 2"):
        block.load_topic_map(path)


def test_an_id_equal_to_an_earlier_alias_raises(tmp_path):
    path = write_lines(tmp_path / "t.jsonl", [row("a", aliases=["b"]), row("b")])
    with pytest.raises(ValueError, match="line 2"):
        block.load_topic_map(path)


def test_an_alias_used_twice_raises(tmp_path):
    path = write_lines(
        tmp_path / "t.jsonl",
        [row("a", aliases=["same"]), row("b", aliases=["same"])],
    )
    with pytest.raises(ValueError, match="line 2"):
        block.load_topic_map(path)


# --- area_of -----------------------------------------------------------------------


def test_area_of_uses_the_group_before_the_colon():
    assert block.area_of("hallmarks: senescence", small_map()) == "How we age"
    assert block.area_of("hallmarks: cellular senescence", small_map()) == "How we age"


def test_area_of_a_topic_without_a_colon():
    assert block.area_of("rapamycin", small_map()) == "Drugs & treatments"


def test_area_of_slugs_the_group():
    assert block.area_of("NAD+ boosters", small_map()) == "Supplements"
    assert block.area_of("NAD+ boosters: NMN", small_map()) == "Supplements"


def test_area_of_finds_a_topic_through_an_alias():
    assert block.area_of("Physical Activity", small_map()) == "Lifestyle"
    assert block.area_of("physical-activity: zone 2", small_map()) == "Lifestyle"


def test_area_of_an_unknown_topic_is_none():
    assert block.area_of("gardening", small_map()) is None
    assert block.area_of("gardening: roses", small_map()) is None


def test_area_of_with_no_topics_is_none():
    assert block.area_of("hallmarks", []) is None


# --- parts -------------------------------------------------------------------------


def test_parts_default_to_empty_and_are_read(tmp_path):
    path = write_lines(
        tmp_path / "t.jsonl", [row("a"), row("b", parts=["One part", "Another"])]
    )
    a, b = block.load_topic_map(path)
    assert a.parts == []
    assert b.parts == ["One part", "Another"]


def test_a_repeated_part_by_slug_raises_naming_the_line(tmp_path):
    path = write_lines(
        tmp_path / "t.jsonl",
        [row("a"), row("b", parts=["Dysbiosis", "Senescence", "dysbiosis"])],
    )
    with pytest.raises(ValueError, match="line 2"):
        block.load_topic_map(path)


@pytest.mark.parametrize("blank", ["", "---", "  "])
def test_a_blank_part_raises_naming_the_line(tmp_path, blank):
    path = write_lines(
        tmp_path / "t.jsonl", [row("a"), row("b", parts=["Dysbiosis", blank])]
    )
    with pytest.raises(ValueError, match="line 2"):
        block.load_topic_map(path)


# --- coverage_lines ----------------------------------------------------------------

PARTS = ["Cellular senescence", "Telomere attrition", "Dysbiosis"]
HEADER_TAIL = "parts covered (each needs an easy what card and a how card)"
NEEDS_BOTH = "(needs: easy what, a how card)"


def parts_map():
    return [
        topic("hallmarks", "How we age", aliases=["hallmarks-of-aging"], parts=PARTS),
        topic("rapamycin", "Drugs & treatments"),
        topic("exercise", "Lifestyle", parts=["Zone 2"]),
    ]


def part_line(lines, part):
    found = [x for x in lines[1:] if x.startswith(f"  {part}:")]
    assert len(found) == 1, lines
    return found[0]


def test_coverage_first_line_counts_covered_parts():
    cards = [
        make_card("c-1", "hallmarks: cellular senescence", "name", "easy"),
        make_card("c-2", "hallmarks: cellular senescence", "explain", "easy"),
        make_card("c-3", "hallmarks: telomere attrition", "name", "easy"),
    ]
    lines = block.coverage_lines(cards, parts_map(), "hallmarks")
    assert lines[0] == f"hallmarks: 1 of 3 {HEADER_TAIL}"


def test_coverage_with_no_cards_covers_nothing():
    lines = block.coverage_lines([], parts_map(), "hallmarks")
    assert lines[0] == f"hallmarks: 0 of 3 {HEADER_TAIL}"
    assert len(lines) == 4
    for part in PARTS:
        assert part_line(lines, part) == (
            f"  {part}: 0 easy what, 0 how; 0 hard {NEEDS_BOTH}"
        )


def test_coverage_easy_name_and_explain_is_ticked():
    cards = [
        make_card("c-1", "hallmarks: cellular senescence", "name", "easy"),
        make_card("c-2", "hallmarks: cellular senescence", "explain", "easy"),
    ]
    lines = block.coverage_lines(cards, parts_map(), "hallmarks")
    assert part_line(lines, "Cellular senescence") == (
        "  Cellular senescence: 1 easy what, 1 how; 0 hard ✓"
    )


def test_coverage_easy_name_and_hard_explain_is_ticked():
    """A how counts at any level; the hard explain also counts in hard."""
    cards = [
        make_card("c-1", "hallmarks: dysbiosis", "name", "easy"),
        make_card("c-2", "hallmarks: dysbiosis", "explain", "hard"),
    ]
    lines = block.coverage_lines(cards, parts_map(), "hallmarks")
    assert part_line(lines, "Dysbiosis") == (
        "  Dysbiosis: 1 easy what, 1 how; 1 hard ✓"
    )
    assert lines[0] == f"hallmarks: 1 of 3 {HEADER_TAIL}"


def test_coverage_easy_name_and_untagged_explain_is_ticked():
    """An untagged explain counts as the how and also as hard."""
    cards = [
        make_card("c-1", "hallmarks: dysbiosis", "name", "easy"),
        make_card("c-2", "hallmarks: dysbiosis", "explain", None),
    ]
    lines = block.coverage_lines(cards, parts_map(), "hallmarks")
    assert part_line(lines, "Dysbiosis") == (
        "  Dysbiosis: 1 easy what, 1 how; 1 hard ✓"
    )


def test_coverage_hard_name_and_easy_explain_needs_easy_what():
    cards = [
        make_card("c-1", "hallmarks: dysbiosis", "name", "hard"),
        make_card("c-2", "hallmarks: dysbiosis", "explain", "easy"),
    ]
    lines = block.coverage_lines(cards, parts_map(), "hallmarks")
    assert part_line(lines, "Dysbiosis") == (
        "  Dysbiosis: 0 easy what, 1 how; 1 hard (needs: easy what)"
    )


def test_coverage_easy_term_counts_as_what():
    cards = [
        make_card("c-1", "hallmarks: dysbiosis", "term", "easy"),
        make_card("c-2", "hallmarks: dysbiosis", "name", "easy"),
    ]
    lines = block.coverage_lines(cards, parts_map(), "hallmarks")
    assert part_line(lines, "Dysbiosis") == (
        "  Dysbiosis: 2 easy what, 0 how; 0 hard (needs: a how card)"
    )


def test_coverage_only_easy_how_needs_easy_what():
    cards = [make_card("c-1", "hallmarks: dysbiosis", "explain", "easy")]
    lines = block.coverage_lines(cards, parts_map(), "hallmarks")
    assert part_line(lines, "Dysbiosis") == (
        "  Dysbiosis: 0 easy what, 1 how; 0 hard (needs: easy what)"
    )


def test_coverage_only_hard_cards_needs_both_and_counts_hard():
    cards = [
        make_card("c-1", "hallmarks: telomere attrition", "name", "hard"),
        make_card("c-2", "hallmarks: telomere attrition", "term", "hard"),
        make_card("c-3", "hallmarks: telomere attrition", "fact", "hard"),
    ]
    lines = block.coverage_lines(cards, parts_map(), "hallmarks")
    assert part_line(lines, "Telomere attrition") == (
        f"  Telomere attrition: 0 easy what, 0 how; 3 hard {NEEDS_BOTH}"
    )


def test_coverage_easy_fact_counts_as_what():
    cards = [
        make_card("c-1", "hallmarks: dysbiosis", "fact", "easy"),
        make_card("c-2", "hallmarks: dysbiosis", "explain", "easy"),
    ]
    lines = block.coverage_lines(cards, parts_map(), "hallmarks")
    assert part_line(lines, "Dysbiosis") == (
        "  Dysbiosis: 1 easy what, 1 how; 0 hard ✓"
    )


@pytest.mark.parametrize("topic_id", ["Hallmarks", "hallmarks-of-aging", "HALLMARKS"])
def test_coverage_finds_topic_id_like_a_card_group(topic_id):
    """Slugged, by id or alias: "Hallmarks" and an alias work like the id."""
    cards = [
        make_card("c-1", "hallmarks: cellular senescence", "name", "easy"),
        make_card("c-2", "hallmarks: cellular senescence", "explain", "easy"),
    ]
    lines = block.coverage_lines(cards, parts_map(), topic_id)
    assert lines[1:] == block.coverage_lines(cards, parts_map(), "hallmarks")[1:]
    assert f" 1 of 3 {HEADER_TAIL}" in lines[0]


def test_coverage_untagged_cards_count_as_hard():
    cards = [
        make_card("c-1", "hallmarks: dysbiosis", "name", None),
        make_card("c-2", "hallmarks: dysbiosis", "fact", None),
    ]
    lines = block.coverage_lines(cards, parts_map(), "hallmarks")
    assert part_line(lines, "Dysbiosis") == (
        f"  Dysbiosis: 0 easy what, 0 how; 2 hard {NEEDS_BOTH}"
    )


def test_coverage_matches_card_topics_by_slug_and_alias():
    cards = [
        make_card("c-1", "Hallmarks: Cellular Senescence", "name", "easy"),
        make_card("c-2", "hallmarks-of-aging: cellular-senescence", "explain", "easy"),
    ]
    lines = block.coverage_lines(cards, parts_map(), "hallmarks")
    assert part_line(lines, "Cellular senescence").endswith(
        "1 easy what, 1 how; 0 hard ✓"
    )
    assert lines[0].startswith("hallmarks: 1 of 3 ")


def test_coverage_card_on_the_topic_alone_counts_for_no_part():
    cards = [
        make_card("c-1", "hallmarks", "name", "easy"),
        make_card("c-2", "hallmarks", "explain", "hard"),
        make_card("c-3", "rapamycin: cellular senescence", "name", "easy"),
    ]
    lines = block.coverage_lines(cards, parts_map(), "hallmarks")
    for part in PARTS:
        assert "0 easy what, 0 how; 0 hard" in part_line(lines, part)


def test_coverage_lists_parts_in_the_topics_order():
    lines = block.coverage_lines([], parts_map(), "hallmarks")
    assert [x.split(":")[0].strip() for x in lines[1:]] == PARTS


@pytest.mark.parametrize("topic_id", ["gardening", "rapamycin"])
def test_coverage_unknown_or_partless_topic_names_topics_with_parts(topic_id):
    with pytest.raises(ValueError) as err:
        block.coverage_lines([], parts_map(), topic_id)
    message = str(err.value)
    assert "hallmarks" in message and "exercise" in message


# --- misfiled ----------------------------------------------------------------------


def test_misfiled_names_a_card_on_an_unknown_part():
    cards = [make_card("c-1", "hallmarks: telomeres")]
    assert block.misfiled(cards, parts_map()) == [
        "c-1: 'telomeres' isn't one of hallmarks's parts"
    ]


def test_misfiled_names_a_card_filed_through_the_alias():
    cards = [
        make_card("c-1", "hallmarks-of-aging: telomeres"),
        make_card("c-2", "Hallmarks of Aging: dysbiosis"),
    ]
    lines = block.misfiled(cards, parts_map())
    assert len(lines) == 1
    assert lines == ["c-1: 'telomeres' isn't one of hallmarks's parts"]


def test_misfiled_leaves_out_well_filed_cards():
    cards = [
        make_card("c-1", "hallmarks: telomere attrition"),
        make_card("c-2", "Hallmarks: Cellular Senescence"),
        make_card("c-3", "hallmarks"),
        make_card("c-4", "rapamycin: mTOR"),
        make_card("c-5", "gardening: roses"),
    ]
    assert block.misfiled(cards, parts_map()) == []


def test_misfiled_one_line_per_bad_card():
    cards = [
        make_card("c-1", "hallmarks: telomeres"),
        make_card("c-2", "hallmarks: dysbiosis"),
        make_card("c-3", "exercise: zone 5"),
    ]
    lines = block.misfiled(cards, parts_map())
    assert len(lines) == 2
    assert lines[0].startswith("c-1: ") and "hallmarks" in lines[0]
    assert lines[1] == "c-3: 'zone 5' isn't one of exercise's parts"


# --- CHAPTERS and syllabus_lines ---------------------------------------------------

CHAPTER_NAMES = {
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
LATER = "Later (dated facts, wait for M5): "
READ = "Read, don't quiz: "
OTHER = "Other status: "


def test_chapters_are_the_24_named_chapters():
    assert block.CHAPTERS == CHAPTER_NAMES
    assert sorted(block.CHAPTERS) == list(range(24))


def stopic(
    id_, primer="", kinds=(), status="v1", aliases=(), parts=None, priority=None
):
    """A Topic for the syllabus tests (area doesn't matter there)."""
    extra = {} if parts is None else {"parts": list(parts)}
    if priority is not None:
        extra["priority"] = priority
    return block.Topic(
        id=id_,
        topic=f"The topic {id_}",
        group="g",
        area="How we age",
        status=status,
        aliases=list(aliases),
        primer=primer,
        kinds=list(kinds),
        **extra,
    )


def syllabus_map():
    """Chapters out of file order; one with parts, after-m5 + read, one chapterless."""
    return [
        stopic("blood", primer="11.4-11.5", kinds=["grade"]),
        stopic("hallmarks", primer="2.1", parts=["Senescence", "Dysbiosis"]),
        stopic("deals", primer="20", status="after-m5"),
        stopic("essay", primer="21", status="read"),
        stopic("aging", primer="1.2", kinds=["term", "explain"], aliases=["ageing"]),
        stopic("misc"),
        stopic("dials", primer="2", kinds=["explain"]),
    ]


def syllabus_cards():
    return [
        make_card("c-1", "aging", "term", "easy"),
        make_card("c-2", "Ageing: why", "explain", "easy"),  # through the alias
        make_card("c-3", "aging", "name", "hard"),
        make_card("c-4", "hallmarks: senescence", "name", "easy"),
        make_card("c-5", "hallmarks: senescence", "explain", "easy"),
        make_card("c-6", "dials", "name", "easy"),
        make_card("c-7", "misc", "explain", "easy"),
        make_card("c-8", "deals", "name", "easy"),
    ]


def test_syllabus_lines_whole_report():
    assert block.syllabus_lines(syllabus_cards(), syllabus_map()) == [
        "Syllabus: 2 of 5 sub-topics covered (an easy what card and a how card)",
        "By priority: core 0 of 0, useful 0 of 0, extra 0 of 0, none 2 of 5",
        "01 What ageing is: 1 of 1 covered",
        "  aging: 1 easy what, 1 how; 1 hard ✓",
        "02 Hallmarks and pathways: 0 of 2 covered",
        "  hallmarks: 1 of 2 parts covered (see: coverage hallmarks)",
        "  dials: 1 easy what, 0 how; 0 hard (needs: a how card)",
        "11 Blood tests: 0 of 1 covered",
        "  blood: 0 easy what, 0 how; 0 hard (needs: an easy card)",
        "?? no chapter: 1 of 1 covered",
        "  misc: 0 easy what, 1 how; 0 hard ✓",
        f"{LATER}1 sub-topics",
        f"{READ}1 sub-topics",
    ]


def topic_line(lines, id_):
    found = [x for x in lines if x.startswith(f"  {id_}:")]
    assert len(found) == 1, lines
    return found[0]


def one(id_, cards, **kw):
    """The report line for a single topic `id_` built from `kw`."""
    return topic_line(block.syllabus_lines(cards, [stopic(id_, **kw)]), id_)


TERM_EXPLAIN = {"primer": "1.3", "kinds": ["term", "explain"]}


def test_syllabus_easy_term_and_explain_is_ticked():
    cards = [
        make_card("c-1", "t", "term", "easy"),
        make_card("c-2", "t", "explain", "easy"),
    ]
    assert one("t", cards, **TERM_EXPLAIN) == "  t: 1 easy what, 1 how; 0 hard ✓"


def test_syllabus_only_easy_term_needs_a_how_card():
    cards = [make_card("c-1", "t", "term", "easy")]
    assert one("t", cards, **TERM_EXPLAIN) == (
        "  t: 1 easy what, 0 how; 0 hard (needs: a how card)"
    )


def test_syllabus_only_hard_cards_needs_both_and_counts_hard():
    cards = [
        make_card("c-1", "t", "term", "hard"),
        make_card("c-2", "t", "fact", "hard"),
        make_card("c-3", "t", "name", None),  # untagged counts as hard
    ]
    assert one("t", cards, **TERM_EXPLAIN) == (
        f"  t: 0 easy what, 0 how; 3 hard {NEEDS_BOTH}"
    )


def test_syllabus_kinds_explain_needs_only_a_how_card():
    kw = {"primer": "1", "kinds": ["explain"]}
    assert one("t", [make_card("c-1", "t", "explain", "easy")], **kw) == (
        "  t: 0 easy what, 1 how; 0 hard ✓"
    )
    assert one("t", [make_card("c-1", "t", "name", "easy")], **kw) == (
        "  t: 1 easy what, 0 how; 0 hard (needs: a how card)"
    )


def test_syllabus_hard_explain_counts_as_the_how():
    cards = [
        make_card("c-1", "t", "term", "easy"),
        make_card("c-2", "t", "explain", "hard"),
    ]
    assert one("t", cards, **TERM_EXPLAIN) == "  t: 1 easy what, 1 how; 1 hard ✓"
    kw = {"primer": "1", "kinds": ["explain"]}
    assert one("t", [make_card("c-1", "t", "explain", "hard")], **kw) == (
        "  t: 0 easy what, 1 how; 1 hard ✓"
    )


@pytest.mark.parametrize("kinds", [["name"], ["fact"], ["term"]])
def test_syllabus_recall_kinds_need_only_an_easy_what(kinds):
    cards = [make_card("c-1", "t", "fact", "easy")]
    assert one("t", cards, primer="1", kinds=kinds) == (
        "  t: 1 easy what, 0 how; 0 hard ✓"
    )


@pytest.mark.parametrize("kinds", [["grade"], []])
def test_syllabus_no_what_or_how_kinds_need_any_easy_card(kinds):
    hard = [make_card("c-1", "t", "name", "hard")]
    assert one("t", hard, primer="1", kinds=kinds) == (
        "  t: 0 easy what, 0 how; 1 hard (needs: an easy card)"
    )
    easy = [make_card("c-1", "t", "explain", "easy")]
    assert one("t", easy, primer="1", kinds=kinds) == (
        "  t: 0 easy what, 1 how; 0 hard ✓"
    )


@pytest.mark.parametrize("kinds", [["grade"], []])
def test_syllabus_no_kinds_lone_hard_explain_still_needs_an_easy_card(kinds):
    hard = [make_card("c-1", "t", "explain", "hard")]
    assert one("t", hard, primer="1", kinds=kinds) == (
        "  t: 0 easy what, 1 how; 1 hard (needs: an easy card)"
    )


def test_syllabus_topic_with_parts_covered_only_when_every_part_is():
    topics = [stopic("h", primer="2.1", parts=["One", "Two"])]
    half = [
        make_card("c-1", "h: one", "name", "easy"),
        make_card("c-2", "h: one", "explain", "easy"),
        make_card("c-3", "h: two", "name", "easy"),
    ]
    lines = block.syllabus_lines(half, topics)
    assert topic_line(lines, "h") == "  h: 1 of 2 parts covered (see: coverage h)"
    assert (
        lines[0]
        == "Syllabus: 0 of 1 sub-topics covered (an easy what card and a how card)"
    )
    full = [*half, make_card("c-4", "h: two", "explain", "easy")]
    lines = block.syllabus_lines(full, topics)
    assert topic_line(lines, "h") == "  h: 2 of 2 parts covered (see: coverage h) ✓"
    assert (
        lines[0]
        == "Syllabus: 1 of 1 sub-topics covered (an easy what card and a how card)"
    )
    assert "02 Hallmarks and pathways: 1 of 1 covered" in lines


def test_syllabus_topic_with_parts_and_a_non_slug_id_is_counted():
    """Parts are counted on the topic itself, not looked up again by its id."""
    topics = [
        stopic("Hall_marks", primer="2.1", aliases=["hall-marks"], parts=["One", "Two"])
    ]
    half = [
        make_card("c-1", "Hall marks: one", "name", "easy"),
        make_card("c-2", "hall-marks: one", "explain", "easy"),
    ]
    lines = block.syllabus_lines(half, topics)
    assert topic_line(lines, "Hall_marks") == (
        "  Hall_marks: 1 of 2 parts covered (see: coverage Hall_marks)"
    )
    full = [
        *half,
        make_card("c-3", "hall-marks: two", "fact", "easy"),
        make_card("c-4", "hall-marks: two", "explain", "easy"),
    ]
    lines = block.syllabus_lines(full, topics)
    assert topic_line(lines, "Hall_marks") == (
        "  Hall_marks: 2 of 2 parts covered (see: coverage Hall_marks) ✓"
    )
    assert (
        lines[0]
        == "Syllabus: 1 of 1 sub-topics covered (an easy what card and a how card)"
    )


@pytest.mark.parametrize(
    ("primer", "header"),
    [
        ("11.4-11.5", "11 Blood tests: 0 of 1 covered"),
        ("5", "05 Consumer longevity: 0 of 1 covered"),
        ("0.2", "00 How to read the evidence: 0 of 1 covered"),
        ("2.1", "02 Hallmarks and pathways: 0 of 1 covered"),
    ],
)
def test_syllabus_chapter_is_the_leading_whole_number(primer, header):
    lines = block.syllabus_lines([], [stopic("t", primer=primer)])
    assert lines[2] == header
    assert lines[3].startswith("  t: ")


def test_syllabus_chapter_missing_from_chapters_uses_chapter_k():
    lines = block.syllabus_lines([], [stopic("t", primer="99.1")])
    assert lines[2] == "99 chapter 99: 0 of 1 covered"


@pytest.mark.parametrize("primer", ["", "Appendix", "A.1"])
def test_syllabus_no_leading_number_goes_under_no_chapter_last(primer):
    topics = [stopic("x", primer=primer), stopic("y", primer="3.1")]
    lines = block.syllabus_lines([], topics)
    assert lines[2] == "03 Big ideas: 0 of 1 covered"
    assert lines[-4:] == [
        "?? no chapter: 0 of 1 covered",
        "  x: 0 easy what, 0 how; 0 hard (needs: an easy card)",
        f"{LATER}0 sub-topics",
        f"{READ}0 sub-topics",
    ]


def test_syllabus_chapters_in_number_order_topics_in_file_order():
    lines = block.syllabus_lines([], syllabus_map())
    headers = [x for x in lines if not x.startswith("  ")]
    assert headers[1].startswith("By priority: ")
    assert [x[:3] for x in headers[2:-2]] == ["01 ", "02 ", "11 ", "?? "]
    ids = [x.split(":")[0].strip() for x in lines if x.startswith("  ")]
    assert ids == ["aging", "hallmarks", "dials", "blood", "misc"]


def test_syllabus_after_m5_and_read_topics_are_counted_not_listed():
    topics = [
        stopic("a", primer="1"),
        stopic("b", primer="20", status="after-m5"),
        stopic("c", primer="21", status="read"),
        stopic("d", primer="22", status="after-m5"),
    ]
    lines = block.syllabus_lines([], topics)
    assert (
        lines[0]
        == "Syllabus: 0 of 1 sub-topics covered (an easy what card and a how card)"
    )
    assert lines[-2:] == [f"{LATER}2 sub-topics", f"{READ}1 sub-topics"]
    assert not any(x.startswith(OTHER) for x in lines)
    assert not any(x.startswith(("  b:", "  c:", "  d:", "20 ", "21 ")) for x in lines)


def test_syllabus_always_has_later_and_read_lines():
    lines = block.syllabus_lines([], [stopic("a", primer="1")])
    assert lines[-2:] == [f"{LATER}0 sub-topics", f"{READ}0 sub-topics"]


def test_syllabus_other_statuses_add_a_last_other_status_line():
    topics = [
        stopic("a", primer="1"),
        stopic("b", primer="20", status="after-m5"),
        stopic("c", primer="21", status="draft"),
    ]
    lines = block.syllabus_lines([], topics)
    assert lines[-3:] == [
        f"{LATER}1 sub-topics",
        f"{READ}0 sub-topics",
        f"{OTHER}1 sub-topics",
    ]
    assert not any(x.startswith(("  c:", "21 ")) for x in lines)


def test_syllabus_card_filed_through_an_alias_counts_for_its_topic():
    cards = [
        make_card("c-1", "Physical Activity", "term", "easy"),
        make_card("c-2", "physical-activity: zone 2", "explain", "easy"),
    ]
    topics = [
        stopic("exercise", "10.2", ["term", "explain"], aliases=["physical-activity"])
    ]
    lines = block.syllabus_lines(cards, topics)
    assert topic_line(lines, "exercise") == "  exercise: 1 easy what, 1 how; 0 hard ✓"


# --- priority -----------------------------------------------------------------------


def test_priority_defaults_to_empty_on_a_topic_built_directly():
    assert topic("a", "How we age").priority == ""


def test_a_non_v1_line_without_a_priority_loads_as_empty(tmp_path):
    path = write_lines(tmp_path / "t.jsonl", [row("a", status="after-m5")])
    assert block.load_topic_map(path)[0].priority == ""


def test_core_useful_extra_and_empty_priorities_load(tmp_path):
    path = write_lines(
        tmp_path / "t.jsonl",
        [
            row("a", priority="core"),
            row("b", priority="useful"),
            row("c", priority="extra"),
        ],
    )
    got = [t.priority for t in block.load_topic_map(path)]
    assert got == ["core", "useful", "extra"]


@pytest.mark.parametrize("bad", ["high", "Core", 1], ids=["high", "capital", "int"])
def test_an_unknown_priority_raises_naming_the_line(tmp_path, bad):
    path = write_lines(tmp_path / "t.jsonl", [row("a"), row("b", priority=bad)])
    with pytest.raises(ValueError, match=r"line 2.*priority"):
        block.load_topic_map(path)


@pytest.mark.parametrize("empty", [None, ""], ids=["missing", "empty"])
def test_a_v1_line_without_a_priority_raises_naming_the_line(tmp_path, empty):
    bad = {k: v for k, v in row("b").items() if k != "priority"}
    if empty is not None:
        bad["priority"] = empty
    path = write_lines(tmp_path / "t.jsonl", [row("a"), bad])
    with pytest.raises(ValueError, match="line 2"):
        block.load_topic_map(path)


@pytest.mark.parametrize("status", ["after-m5", "read"])
def test_a_non_v1_line_with_a_priority_raises_naming_the_line(tmp_path, status):
    path = write_lines(
        tmp_path / "t.jsonl", [row("a"), row("b", status=status, priority="core")]
    )
    with pytest.raises(ValueError, match="line 2"):
        block.load_topic_map(path)


def priority_map():
    """Every tier; uncovered and covered, a non-v1, parts, a chapterless one."""
    return [
        stopic("gompertz", "1.1", ["term", "explain"], priority="core"),
        stopic("x", "", ["fact"], priority="extra"),
        stopic("healthspan", "1.2", ["name", "explain"], priority="useful"),
        stopic("evidence-grades", "0.3", ["grade"], priority="core"),
        stopic("done", "3", ["explain"], priority="core"),
        stopic("later", "20", status="after-m5", priority="core"),
        stopic("nopri", "5"),
        stopic("hallmarks", "2.1", parts=["One", "Two"], priority="core"),
    ]


def priority_cards():
    return [
        make_card("c-1", "gompertz", "term", "easy"),
        make_card("c-2", "evidence-grades", "name", "hard"),
        make_card("c-3", "done", "explain", "easy"),
        make_card("c-4", "hallmarks: one", "name", "easy"),
        make_card("c-5", "hallmarks: one", "explain", "easy"),
        make_card("c-6", "x", "explain", "easy"),
    ]


def test_syllabus_second_line_counts_each_tier_and_none():
    lines = block.syllabus_lines(priority_cards(), priority_map())
    assert lines[1] == (
        "By priority: core 1 of 4, useful 0 of 1, extra 0 of 1, none 0 of 1"
    )


def test_syllabus_second_line_empty_tiers_are_0_of_0_and_no_none_part():
    topics = [
        stopic("a", "1", ["explain"], priority="core"),
        stopic("b", "1", ["explain"], priority="core"),
        stopic("c", "20", status="read"),  # not v1: no "none" part
    ]
    cards = [make_card("c-1", "a", "explain", "easy")]
    lines = block.syllabus_lines(cards, topics)
    assert lines[1] == "By priority: core 1 of 2, useful 0 of 0, extra 0 of 0"


# --- todo_lines ----------------------------------------------------------------------


def test_todo_lines_whole_report():
    assert block.todo_lines(priority_cards(), priority_map()) == [
        "Core: 3 to fill",
        "  01 gompertz: needs a how card",
        "  00 evidence-grades: needs an easy card",
        "  02 hallmarks: 1 of 2 parts covered",
        "Useful: 1 to fill",
        "  01 healthspan: needs easy what, a how card",
        "Extra: 1 to fill",
        "  ?? x: needs easy what",
        "No priority: 1 to fill",
        "  05 nopri: needs an easy card",
    ]


def test_todo_lines_leaves_out_covered_and_non_v1_topics():
    lines = block.todo_lines(priority_cards(), priority_map())
    assert not any(" done:" in x or " later:" in x for x in lines)


def test_todo_lines_skips_a_tier_with_nothing_to_fill():
    topics = [
        stopic("a", "1", ["explain"], priority="extra"),
        stopic("b", "1", ["explain"], priority="useful"),
        stopic("c", "1", ["explain"], priority="core"),
    ]
    cards = [make_card("c-1", "b", "explain", "easy")]
    assert block.todo_lines(cards, topics) == [
        "Core: 1 to fill",
        "  01 c: needs a how card",
        "Extra: 1 to fill",
        "  01 a: needs a how card",
    ]


def test_todo_lines_topic_with_parts_counts_its_parts():
    topics = [stopic("hallmarks", "2.1", parts=PARTS, priority="core")]
    cards = [
        make_card("c-1", "hallmarks: dysbiosis", "fact", "easy"),
        make_card("c-2", "hallmarks: dysbiosis", "explain", "easy"),
    ]
    assert block.todo_lines(cards, topics) == [
        "Core: 1 to fill",
        "  02 hallmarks: 1 of 3 parts covered",
    ]


def test_todo_lines_nothing_to_fill_is_one_line():
    topics = [
        stopic("a", "1", ["explain"], priority="core"),
        stopic("b", "20", status="after-m5", priority="core"),
    ]
    cards = [make_card("c-1", "a", "explain", "easy")]
    assert block.todo_lines(cards, topics) == [
        "Nothing to fill: every sub-topic is covered"
    ]


def test_todo_lines_with_no_topics_has_nothing_to_fill():
    assert block.todo_lines([], []) == ["Nothing to fill: every sub-topic is covered"]


# --- CLI: longevity coverage -------------------------------------------------------


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    """A temporary topic file and card folder, wired into both lookups."""
    from longevity_trainer import cli

    topics_path = write_lines(
        tmp_path / "topics.jsonl",
        [row("hallmarks", parts=PARTS), row("rapamycin", area="Drugs & treatments")],
    )
    cards_dir = tmp_path / "cards"
    cards_dir.mkdir()
    cards = [
        make_card("c-1", "hallmarks: cellular senescence", "name", "easy"),
        make_card("c-2", "hallmarks: cellular senescence", "explain", "easy"),
        make_card("c-3", "hallmarks: dysbiosis", "fact", "hard"),
    ]
    (cards_dir / "hallmarks.jsonl").write_text(
        "\n".join(c.model_dump_json() for c in cards) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(block, "TOPICS_FILE", topics_path)
    monkeypatch.setattr(cli, "TOPICS_FILE", topics_path, raising=False)
    monkeypatch.setattr(cli, "CARDS_DIR", cards_dir)
    monkeypatch.setattr(cli, "load_cards", lambda d=cards_dir: load_cards(d))
    return cli, cards, block.load_topic_map(topics_path)


def test_cli_coverage_prints_the_lines(cli_env, capsys):
    cli, cards, topics = cli_env
    code = cli.main(["coverage", "hallmarks"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.splitlines() == block.coverage_lines(cards, topics, "hallmarks")
    assert out.splitlines()[0] == f"hallmarks: 1 of 3 {HEADER_TAIL}"


@pytest.mark.parametrize("topic_id", ["gardening", "rapamycin"])
def test_cli_coverage_unknown_topic_one_line_exit_1(cli_env, capsys, topic_id):
    cli, _, _ = cli_env
    code = cli.main(["coverage", topic_id])
    captured = capsys.readouterr()
    lines = (captured.out + captured.err).strip().splitlines()
    assert code == 1
    assert len(lines) == 1
    assert "hallmarks" in lines[0]


def test_cli_coverage_with_no_topic_prints_the_syllabus(cli_env, capsys):
    cli, cards, topics = cli_env
    code = cli.main(["coverage"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.splitlines() == block.syllabus_lines(cards, topics)
    assert out.splitlines()[0].startswith("Syllabus: ")


def test_cli_coverage_todo_prints_the_todo_lines(cli_env, capsys):
    cli, cards, topics = cli_env
    code = cli.main(["coverage", "--todo"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.splitlines() == block.todo_lines(cards, topics)
    assert out.splitlines()[0] == "Core: 2 to fill"


def test_cli_coverage_todo_with_a_topic_is_an_argparse_error(cli_env, capsys):
    cli, _, _ = cli_env
    try:
        code = cli.main(["coverage", "--todo", "hallmarks"])
    except SystemExit as stop:
        code = stop.code
    assert code == 2


def test_cli_coverage_todo_with_an_empty_topic_is_an_argparse_error(cli_env, capsys):
    cli, _, _ = cli_env
    try:
        code = cli.main(["coverage", "", "--todo"])
    except SystemExit as stop:
        code = stop.code
    assert code == 2


def test_coverage_command_with_a_topic_and_todo_one_line_exit_1(cli_env, capsys):
    """Called directly (no argparse): a topic with todo=True is refused."""
    cli, _, _ = cli_env
    code = cli.coverage_command("hallmarks", todo=True)
    captured = capsys.readouterr()
    lines = (captured.out + captured.err).strip().splitlines()
    assert code == 1
    assert len(lines) == 1, lines


def one_line_exit_1(cli, args, capsys):
    code = cli.main(args)
    captured = capsys.readouterr()
    lines = (captured.out + captured.err).strip().splitlines()
    assert code == 1
    assert len(lines) == 1, lines


CLI_ARGS = [["coverage"], ["coverage", "hallmarks"], ["coverage", "--todo"]]
CLI_IDS = ["no-topic", "topic", "todo"]


@pytest.mark.parametrize("args", CLI_ARGS, ids=CLI_IDS)
def test_cli_coverage_missing_topic_map_one_line_exit_1(
    cli_env, capsys, monkeypatch, tmp_path, args
):
    cli, _, _ = cli_env
    gone = tmp_path / "gone.jsonl"
    monkeypatch.setattr(block, "TOPICS_FILE", gone)
    monkeypatch.setattr(cli, "TOPICS_FILE", gone, raising=False)
    one_line_exit_1(cli, args, capsys)


@pytest.mark.parametrize("args", CLI_ARGS, ids=CLI_IDS)
def test_cli_coverage_not_json_topic_map_one_line_exit_1(cli_env, capsys, args):
    cli, _, _ = cli_env
    block.TOPICS_FILE.write_text("{not json\n", encoding="utf-8")
    one_line_exit_1(cli, args, capsys)


@pytest.mark.parametrize("args", CLI_ARGS, ids=CLI_IDS)
def test_cli_coverage_bad_card_file_one_line_exit_1(cli_env, capsys, args):
    cli, _, _ = cli_env
    (cli.CARDS_DIR / "broken.jsonl").write_text("{not a card\n", encoding="utf-8")
    one_line_exit_1(cli, args, capsys)


# --- areas_in ----------------------------------------------------------------------


def test_areas_in_gives_shelves_in_areas_order_not_card_order():
    cards = [
        make_card("c-1", "Physical Activity"),
        make_card("c-2", "rapamycin"),
        make_card("c-3", "hallmarks: senescence"),
    ]
    assert block.areas_in(cards, small_map()) == [
        "How we age",
        "Drugs & treatments",
        "Lifestyle",
    ]


def test_areas_in_lists_each_shelf_once():
    cards = [
        make_card("c-1", "hallmarks: senescence"),
        make_card("c-2", "hallmarks: telomeres"),
        make_card("c-3", "hallmarks"),
    ]
    assert block.areas_in(cards, small_map()) == ["How we age"]


def test_areas_in_leaves_out_a_card_with_no_shelf():
    cards = [make_card("c-1", "gardening"), make_card("c-2", "NAD+ boosters")]
    assert block.areas_in(cards, small_map()) == ["Supplements"]


def test_areas_in_with_no_cards_is_empty():
    assert block.areas_in([], small_map()) == []


# --- real data ---------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_map():
    return block.load_topic_map(block.TOPICS_FILE)


def test_the_real_topic_map_loads(real_map):
    assert real_map
    assert all(t.area in AREAS for t in real_map)


def test_every_real_card_has_a_shelf(real_map):
    """A card filed under an unknown name fails CI: alias its topic or use the id."""
    no_shelf = sorted(
        {c.topic for c in load_cards() if block.area_of(c.topic, real_map) is None}
    )
    assert no_shelf == []


def test_real_drugs_and_hallmarks_are_on_the_right_shelves(real_map):
    by_id = {t.id: t for t in real_map}
    assert by_id["rapamycin"].area == "Drugs & treatments"
    assert by_id["metformin"].area == "Drugs & treatments"
    assert by_id["hallmarks"].area == "How we age"
    assert block.area_of("rapamycin", real_map) == "Drugs & treatments"
    assert block.area_of("metformin", real_map) == "Drugs & treatments"
    assert block.area_of("hallmarks: senescence", real_map) == "How we age"
    assert block.area_of("hallmarks: cellular senescence", real_map) == "How we age"


def test_real_exercise_is_found_as_physical_activity(real_map):
    by_id = {t.id: t for t in real_map}
    assert "physical-activity" in by_id["exercise"].aliases
    assert block.area_of("physical-activity", real_map) == by_id["exercise"].area


def test_real_areas_in_is_in_areas_order(real_map):
    shelves = block.areas_in(load_cards(), real_map)
    assert shelves
    assert shelves == [a for a in AREAS if a in shelves]


HALLMARKS_2023 = [
    "genomic instability",
    "telomere attrition",
    "epigenetic alterations",
    "loss of proteostasis",
    "disabled macroautophagy",
    "deregulated nutrient-sensing",
    "mitochondrial dysfunction",
    "cellular senescence",
    "stem cell exhaustion",
    "altered intercellular communication",
    "chronic inflammation",
    "dysbiosis",
]


def norm(text):
    """The SPEC's slug rule, so capitals/hyphens in the data file don't matter."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def test_real_hallmarks_has_the_12_parts_of_the_2023_review(real_map):
    by_id = {t.id: t for t in real_map}
    assert [norm(p) for p in by_id["hallmarks"].parts] == [
        norm(p) for p in HALLMARKS_2023
    ]


def test_real_cards_are_filed_under_real_parts(real_map):
    """Every hallmark card names one hallmark, or is filed under `hallmarks` alone."""
    assert block.misfiled(load_cards(), real_map) == []


def test_real_hallmarks_coverage_report_runs(real_map):
    lines = block.coverage_lines(load_cards(), real_map, "hallmarks")
    assert lines[0].startswith("hallmarks: ")
    assert len(lines) == 1 + len(HALLMARKS_2023)


def test_every_real_v1_topic_has_a_chapter(real_map):
    """Checked on syllabus_lines' own output: no chapterless or unnamed chapter."""
    lines = block.syllabus_lines(load_cards(), real_map)
    headers = [x for x in lines[1:] if re.match(r"\d\d ", x)]
    assert not any(x.startswith("?? ") for x in lines)
    assert not [x for x in headers if re.match(r"\d\d chapter \d+:", x)]
    total = int(re.match(r"Syllabus: \d+ of (\d+) ", lines[0]).group(1))
    counts = [int(re.search(r": \d+ of (\d+) covered$", x).group(1)) for x in headers]
    assert sum(counts) == total
    v1 = [t for t in real_map if t.status == "v1"]
    assert total == len(v1)


def test_every_real_v1_topic_has_a_priority(real_map):
    missing = [
        t.id
        for t in real_map
        if t.status == "v1" and t.priority not in ("core", "useful", "extra")
    ]
    assert missing == []
    second = block.syllabus_lines(load_cards(), real_map)[1]
    assert second.startswith("By priority: core ")
    assert ", none " not in second


def test_real_todo_report_runs(real_map):
    lines = block.todo_lines(load_cards(), real_map)
    assert lines
    assert not any(x.startswith(("No priority:", "  ?? ")) for x in lines)


def test_real_syllabus_report_runs(real_map):
    lines = block.syllabus_lines(load_cards(), real_map)
    assert lines[0].startswith("Syllabus: ")
    assert any(x.startswith(LATER) for x in lines)
    assert any(x.startswith(READ) for x in lines)
    assert not any(x.startswith("?? ") for x in lines)
