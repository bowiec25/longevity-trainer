"""Tests for the topic_map block: its contract (ID card + SPEC.md) and its behaviour.

Written from SPEC.md "How to test", before the code. Names are reached through
`block.<name>` so the contract tests still run while the code isn't built. Small
topic files are written to tmp_path; the real-data tests read data/topics.jsonl
and the real card bank.
"""

import json
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
    assert set(block.BLOCK_SPEC.inputs) == {"path", "card_topic", "topics", "cards"}
    assert set(block.BLOCK_SPEC.outputs) == {
        "TOPICS_FILE",
        "AREAS",
        "Topic",
        "load_topic_map",
        "area_of",
        "areas_in",
    }


# --- helpers ---------------------------------------------------------------------


def row(id_, area="How we age", **extra):
    return {
        "id": id_,
        "topic": f"The topic {id_}",
        "group": "g",
        "area": area,
        "status": "v1",
    } | extra


def write_lines(path, lines):
    """Each item: a dict (written as JSON) or a str (written as is)."""
    text = "\n".join(x if isinstance(x, str) else json.dumps(x) for x in lines)
    path.write_text(text + "\n", encoding="utf-8")
    return path


def topic(id_, area, aliases=()):
    return block.Topic(
        id=id_,
        topic=f"The topic {id_}",
        group="g",
        area=area,
        status="v1",
        aliases=list(aliases),
    )


def small_map():
    return [
        topic("hallmarks", "How we age"),
        topic("rapamycin", "Drugs & treatments"),
        topic("nad-boosters", "Supplements"),
        topic("exercise", "Lifestyle", aliases=["physical-activity"]),
    ]


def make_card(card_id, topic_text):
    return LongevityCard(
        id=card_id,
        kind="name",
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


def test_real_exercise_is_found_as_physical_activity(real_map):
    by_id = {t.id: t for t in real_map}
    assert "physical-activity" in by_id["exercise"].aliases
    assert block.area_of("physical-activity", real_map) == by_id["exercise"].area


def test_real_areas_in_is_in_areas_order(real_map):
    shelves = block.areas_in(load_cards(), real_map)
    assert shelves
    assert shelves == [a for a in AREAS if a in shelves]
