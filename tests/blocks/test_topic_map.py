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
HEADER_TAIL = "parts covered in easy mode (each needs an easy what and how card)"
NEEDS_BOTH = "(needs: easy what, easy how)"


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
            f"  {part}: easy 0 what, 0 how; 0 hard {NEEDS_BOTH}"
        )


def test_coverage_easy_name_and_explain_is_ticked():
    cards = [
        make_card("c-1", "hallmarks: cellular senescence", "name", "easy"),
        make_card("c-2", "hallmarks: cellular senescence", "explain", "easy"),
    ]
    lines = block.coverage_lines(cards, parts_map(), "hallmarks")
    assert part_line(lines, "Cellular senescence") == (
        "  Cellular senescence: easy 1 what, 1 how; 0 hard ✓"
    )


def test_coverage_easy_term_counts_as_what():
    cards = [
        make_card("c-1", "hallmarks: dysbiosis", "term", "easy"),
        make_card("c-2", "hallmarks: dysbiosis", "name", "easy"),
    ]
    lines = block.coverage_lines(cards, parts_map(), "hallmarks")
    assert part_line(lines, "Dysbiosis") == (
        "  Dysbiosis: easy 2 what, 0 how; 0 hard (needs: easy how)"
    )


def test_coverage_only_easy_how_needs_easy_what():
    cards = [make_card("c-1", "hallmarks: dysbiosis", "explain", "easy")]
    lines = block.coverage_lines(cards, parts_map(), "hallmarks")
    assert part_line(lines, "Dysbiosis") == (
        "  Dysbiosis: easy 0 what, 1 how; 0 hard (needs: easy what)"
    )


def test_coverage_only_hard_cards_needs_both_and_counts_hard():
    cards = [
        make_card("c-1", "hallmarks: telomere attrition", "name", "hard"),
        make_card("c-2", "hallmarks: telomere attrition", "explain", "hard"),
        make_card("c-3", "hallmarks: telomere attrition", "fact", "hard"),
    ]
    lines = block.coverage_lines(cards, parts_map(), "hallmarks")
    assert part_line(lines, "Telomere attrition") == (
        f"  Telomere attrition: easy 0 what, 0 how; 3 hard {NEEDS_BOTH}"
    )


def test_coverage_easy_fact_counts_as_what():
    cards = [
        make_card("c-1", "hallmarks: dysbiosis", "fact", "easy"),
        make_card("c-2", "hallmarks: dysbiosis", "explain", "easy"),
    ]
    lines = block.coverage_lines(cards, parts_map(), "hallmarks")
    assert part_line(lines, "Dysbiosis") == (
        "  Dysbiosis: easy 1 what, 1 how; 0 hard ✓"
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
        make_card("c-2", "hallmarks: dysbiosis", "explain", None),
    ]
    lines = block.coverage_lines(cards, parts_map(), "hallmarks")
    assert part_line(lines, "Dysbiosis") == (
        f"  Dysbiosis: easy 0 what, 0 how; 2 hard {NEEDS_BOTH}"
    )


def test_coverage_matches_card_topics_by_slug_and_alias():
    cards = [
        make_card("c-1", "Hallmarks: Cellular Senescence", "name", "easy"),
        make_card("c-2", "hallmarks-of-aging: cellular-senescence", "explain", "easy"),
    ]
    lines = block.coverage_lines(cards, parts_map(), "hallmarks")
    assert part_line(lines, "Cellular senescence").endswith("1 what, 1 how; 0 hard ✓")
    assert lines[0].startswith("hallmarks: 1 of 3 ")


def test_coverage_card_on_the_topic_alone_counts_for_no_part():
    cards = [
        make_card("c-1", "hallmarks", "name", "easy"),
        make_card("c-2", "hallmarks", "explain", "hard"),
        make_card("c-3", "rapamycin: cellular senescence", "name", "easy"),
    ]
    lines = block.coverage_lines(cards, parts_map(), "hallmarks")
    for part in PARTS:
        assert "easy 0 what, 0 how; 0 hard" in part_line(lines, part)


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
