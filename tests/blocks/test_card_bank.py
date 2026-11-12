"""Tests for the card_bank block: the contract (ID card + SPEC.md) and the behaviour.

The behaviour tests are written from SPEC.md alone (test-first). They reach the block
through the module (`block.load_cards`, `block.LongevityCard`, `block.CARDS_DIR`, the
same names as `from longevity_trainer.blocks.card_bank import ...`) so each test fails
on its own until the code exists, instead of the whole file failing at import.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import longevity_trainer.blocks.card_bank as block
from quizkit.blocks.base import missing_spec_sections, spec_section
from quizkit.models import Card

SPEC_MD = Path(block.__file__).parent / "SPEC.md"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
REAL_CARDS = PROJECT_ROOT / "data" / "cards"
KINDS = {"name", "fact", "term", "explain"}


# Contract


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "card_bank"
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


# Helpers


def card(id="c1", **changes) -> dict:
    """A valid card as a dict; `changes` override fields (None removes one)."""
    data = {
        "id": id,
        "kind": "name",
        "topic": "telomere attrition",
        "question": "Which hallmark is the shortening of chromosome ends?",
        "answers": ["telomere attrition", "telomere shortening"],
        "receipt": {
            "source": "hallmarks-of-aging-2023",
            "quote": "telomeres undergo a substantial shortening",
            "page": 9,
        },
    }
    data.update(changes)
    return {k: v for k, v in data.items() if v is not None}


def receipt(**changes) -> dict:
    data = {"source": "s", "quote": "telomeres undergo shortening", "page": 9}
    data.update(changes)
    return data


def write(path: Path, *lines) -> Path:
    """Write lines (dicts become JSON, strings go in as-is) to a .jsonl file."""
    text = "\n".join(json.dumps(x) if isinstance(x, dict) else x for x in lines)
    path.write_text(text + "\n", encoding="utf-8")
    return path


# Loads


def test_loads_files_in_name_order_then_line_order(tmp_path):
    write(tmp_path / "b.jsonl", card("b1"), card("b2"))
    write(tmp_path / "a.jsonl", card("a1"), card("a2"))
    cards = block.load_cards(tmp_path)
    assert [c.id for c in cards] == ["a1", "a2", "b1", "b2"]
    assert all(isinstance(c, block.LongevityCard) for c in cards)


def test_blank_lines_are_skipped(tmp_path):
    write(tmp_path / "a.jsonl", "", card("a1"), "   ", "", card("a2"), "")
    assert [c.id for c in block.load_cards(tmp_path)] == ["a1", "a2"]


def test_only_jsonl_files_are_read(tmp_path):
    write(tmp_path / "a.jsonl", card("a1"))
    (tmp_path / "notes.txt").write_text("not a card\n", encoding="utf-8")
    (tmp_path / "old.json").write_text("{broken", encoding="utf-8")
    assert [c.id for c in block.load_cards(tmp_path)] == ["a1"]


def test_subfolders_are_ignored(tmp_path):
    write(tmp_path / "a.jsonl", card("a1"))
    sub = tmp_path / "drafts"
    sub.mkdir()
    write(sub / "b.jsonl", card("a1"), "{broken")  # repeat + bad line, never read
    (tmp_path / "folder.jsonl").mkdir()  # a folder named like a card file
    assert [c.id for c in block.load_cards(tmp_path)] == ["a1"]


def test_file_starting_with_utf8_bom_loads(tmp_path):
    path = tmp_path / "a.jsonl"
    path.write_bytes(b"\xef\xbb\xbf" + (json.dumps(card("a1")) + "\n").encode())
    (c,) = block.load_cards(tmp_path)
    assert c.id == "a1"


def test_non_utf8_file_raises_value_error_naming_file(tmp_path):
    write(tmp_path / "a.jsonl", card("a1"))
    line = json.dumps(card("b1", topic="café"), ensure_ascii=False)
    (tmp_path / "latin.jsonl").write_bytes(line.encode("latin-1") + b"\n")  # é = 0xE9
    with pytest.raises(ValueError, match=r"latin\.jsonl"):
        block.load_cards(tmp_path)


def test_card_fields_are_loaded(tmp_path):
    write(tmp_path / "a.jsonl", card("a1"))
    (c,) = block.load_cards(tmp_path)
    assert c.kind == "name"
    assert c.topic == "telomere attrition"
    assert c.question == "Which hallmark is the shortening of chromosome ends?"
    assert c.answers == ["telomere attrition", "telomere shortening"]
    assert c.receipt.source == "hallmarks-of-aging-2023"
    assert c.receipt.quote == "telomeres undergo a substantial shortening"
    assert c.receipt.page == 9


def test_receipt_is_the_quizkit_receipt(tmp_path):
    from quizkit.blocks.receipts import Receipt

    write(tmp_path / "a.jsonl", card("a1"))
    (c,) = block.load_cards(tmp_path)
    assert isinstance(c.receipt, Receipt)


def test_surrounding_spaces_are_stripped(tmp_path):
    write(
        tmp_path / "a.jsonl",
        card(
            "  a1 ",
            kind=" fact ",
            topic="  sleep  ",
            question="  What does sleep clear from the brain?  ",
            answers=["  waste  ", " amyloid"],
        ),
    )
    (c,) = block.load_cards(tmp_path)
    assert c.id == "a1"
    assert c.kind == "fact"
    assert c.topic == "sleep"
    assert c.question == "What does sleep clear from the brain?"
    assert c.answers == ["waste", "amyloid"]


@pytest.mark.parametrize("kind", sorted(KINDS))
def test_every_allowed_kind_loads(tmp_path, kind):
    write(tmp_path / "a.jsonl", card("a1", kind=kind))
    assert block.load_cards(tmp_path)[0].kind == kind


def test_card_is_frozen(tmp_path):
    write(tmp_path / "a.jsonl", card("a1"))
    (c,) = block.load_cards(tmp_path)
    with pytest.raises(ValidationError):  # frozen: no changes after loading
        c.id = "changed"


def test_root_and_cards_dir_are_exported():
    from longevity_trainer.blocks.card_bank import CARDS_DIR, ROOT

    assert isinstance(ROOT, Path)
    assert isinstance(CARDS_DIR, Path)
    assert CARDS_DIR == ROOT / "data" / "cards"
    assert ROOT.resolve() == PROJECT_ROOT


def test_default_folder_is_the_project_cards():
    assert Path(block.CARDS_DIR).resolve() == REAL_CARDS.resolve()
    assert [c.id for c in block.load_cards()] == [
        c.id for c in block.load_cards(REAL_CARDS)
    ]


# to_quizkit


def test_to_quizkit_makes_a_quizkit_card(tmp_path):
    write(tmp_path / "a.jsonl", card("a1", kind="term", topic="autophagy"))
    (c,) = block.load_cards(tmp_path)
    q = c.to_quizkit()
    assert isinstance(q, Card)
    assert q.id == "a1"
    assert q.answers == ["telomere attrition", "telomere shortening"]
    assert q.fields == {
        "question": "Which hallmark is the shortening of chromosome ends?",
        "kind": "term",
        "topic": "autophagy",
    }
    assert q.level == 1


# Failure modes: a bad line -> ValueError naming the file and the line number

BAD_LINES = {
    "bad JSON": '{"id": "x", "kind": ',
    "not an object": '["a", "list"]',
    "missing field": card("x", question=None),
    "missing receipt": card("x", receipt=None),
    "unknown field": card("x", difficulty=3),
    "unknown kind": card("x", kind="trivia"),
    "blank answer": card("x", answers=["telomere attrition", "   "]),
    "no answers": card("x", answers=[]),
    "blank id": card("   "),
    "blank topic": card("x", topic="  "),
    "short question": card("x", question="Why age?"),
    "short quote": card("x", receipt=receipt(quote="telomeres")),
    "empty source": card("x", receipt=receipt(source="")),
    "spaces-only source": card("x", receipt=receipt(source="   ")),
    "page zero": card("x", receipt=receipt(page=0)),
    "receipt unknown field": card("x", receipt=receipt(url="https://example.org")),
}


@pytest.mark.parametrize("bad", BAD_LINES.values(), ids=BAD_LINES.keys())
def test_bad_line_raises_value_error_with_file_and_line(tmp_path, bad):
    write(tmp_path / "a.jsonl", card("ok1"))
    write(tmp_path / "hallmarks.jsonl", card("ok2"), card("ok3"), bad)
    with pytest.raises(ValueError) as err:
        block.load_cards(tmp_path)
    message = str(err.value)
    assert "hallmarks.jsonl" in message
    assert "line 3" in message


def test_line_number_counts_blank_lines(tmp_path):
    """Line numbers are the file's own (as in an editor), so blank lines count."""
    write(tmp_path / "a.jsonl", card("ok1"), "", card("x", kind="trivia"))
    with pytest.raises(ValueError, match=r"a\.jsonl line 3"):
        block.load_cards(tmp_path)


def test_question_needs_at_least_ten_characters(tmp_path):
    write(tmp_path / "a.jsonl", card("a1", question="Name it?!!"))  # exactly 10
    assert block.load_cards(tmp_path)[0].question == "Name it?!!"
    write(tmp_path / "a.jsonl", card("a1", question="Name it?!"))  # 9
    with pytest.raises(ValueError, match="line 1"):
        block.load_cards(tmp_path)


def test_model_rejects_unknown_fields_directly():
    with pytest.raises(ValueError):
        block.LongevityCard(**card("x", difficulty=3))


# Failure modes: repeated ids, empty folder, missing folder


def test_repeated_id_in_one_file_raises(tmp_path):
    write(tmp_path / "a.jsonl", card("dup"), card("ok"), card("dup"))
    with pytest.raises(ValueError, match="dup"):
        block.load_cards(tmp_path)


def test_repeated_id_across_files_raises(tmp_path):
    write(tmp_path / "a.jsonl", card("dup-1"), card("dup-2"))
    write(tmp_path / "b.jsonl", card("ok"), card("dup-2"), card("dup-1"))
    with pytest.raises(ValueError) as err:
        block.load_cards(tmp_path)
    assert "dup-1" in str(err.value)
    assert "dup-2" in str(err.value)


def test_empty_folder_raises(tmp_path):
    with pytest.raises(ValueError, match="no cards found"):
        block.load_cards(tmp_path)


def test_folder_without_jsonl_files_raises(tmp_path):
    (tmp_path / "readme.txt").write_text("hello\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no cards found"):
        block.load_cards(tmp_path)


def test_folder_with_only_blank_lines_raises(tmp_path):
    write(tmp_path / "a.jsonl", "", "   ", "")
    (tmp_path / "b.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="no cards found"):
        block.load_cards(tmp_path)


def test_missing_folder_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        block.load_cards(tmp_path / "nope")


# The real bank (a guard on the committed data)


def test_real_bank_loads_at_least_15_valid_cards():
    cards = block.load_cards(REAL_CARDS)
    assert len(cards) >= 15
    assert {c.kind for c in cards} <= KINDS
    assert len({c.id for c in cards}) == len(cards)
    assert all(isinstance(c.to_quizkit(), Card) for c in cards)
