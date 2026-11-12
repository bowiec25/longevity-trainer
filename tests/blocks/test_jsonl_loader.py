"""Tests for the jsonl_loader block: contract (ID card + SPEC.md) and behaviour from SPEC.md."""

import json
from pathlib import Path

import pytest
from pydantic import BaseModel

import quizkit.blocks.jsonl_loader as block
from quizkit.blocks.base import missing_spec_sections, spec_section

SPEC_MD = Path(block.__file__).parent / "SPEC.md"


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "jsonl_loader"
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


# --- Behaviour tests, written from SPEC.md alone -----------------------------


class Row(BaseModel):
    id: str
    n: int


def _write(folder: Path, name: str, text: str) -> Path:
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return path


def _ids(rows):
    return [r.id for r in rows]


# Outputs: every record, in file-name order then line order


def test_loads_files_in_name_order_then_line_order(tmp_path):
    _write(tmp_path, "b.jsonl", '{"id": "b1", "n": 3}\n{"id": "b2", "n": 4}\n')
    _write(tmp_path, "a.jsonl", '{"id": "a1", "n": 1}\n{"id": "a2", "n": 2}\n')
    rows = block.load_jsonl_dir(tmp_path, Row)
    assert _ids(rows) == ["a1", "a2", "b1", "b2"]
    assert all(isinstance(r, Row) for r in rows)
    assert [r.n for r in rows] == [1, 2, 3, 4]


def test_blank_and_spaces_only_lines_are_skipped(tmp_path):
    _write(
        tmp_path, "a.jsonl", '\n{"id": "x", "n": 1}\n   \n\n{"id": "y", "n": 2}\n  \t\n'
    )
    assert _ids(block.load_jsonl_dir(tmp_path, Row)) == ["x", "y"]


def test_non_jsonl_files_and_subfolders_are_ignored(tmp_path):
    _write(tmp_path, "a.jsonl", '{"id": "x", "n": 1}\n')
    _write(tmp_path, "notes.txt", "not json at all\n")
    _write(tmp_path, "a.json", "{broken\n")
    sub = tmp_path / "sub"
    sub.mkdir()
    _write(sub, "b.jsonl", '{"id": "deep", "n": 2}\n')
    assert _ids(block.load_jsonl_dir(tmp_path, Row)) == ["x"]


def test_bom_at_start_of_file_is_fine(tmp_path):
    (tmp_path / "a.jsonl").write_bytes(
        "\ufeff".encode("utf-8") + b'{"id": "x", "n": 1}\n{"id": "y", "n": 2}\n'
    )
    assert _ids(block.load_jsonl_dir(tmp_path, Row)) == ["x", "y"]


def test_file_without_trailing_newline_loads(tmp_path):
    _write(tmp_path, "a.jsonl", '{"id": "x", "n": 1}\n{"id": "y", "n": 2}')
    assert _ids(block.load_jsonl_dir(tmp_path, Row)) == ["x", "y"]


def test_nothing_is_written(tmp_path):
    _write(tmp_path, "a.jsonl", '{"id": "x", "n": 1}\n')
    before = sorted(p.name for p in tmp_path.iterdir())
    block.load_jsonl_dir(tmp_path, Row)
    assert sorted(p.name for p in tmp_path.iterdir()) == before


# Failure mode: bad JSON / model rejects -> "<file name> line <n>: "


def test_invalid_json_names_file_and_line(tmp_path):
    _write(tmp_path, "a.jsonl", '{"id": "x", "n": 1}\n')
    _write(tmp_path, "b.jsonl", '{"id": "y", "n": 2}\n{not json\n')
    with pytest.raises(ValueError) as err:
        block.load_jsonl_dir(tmp_path, Row)
    assert str(err.value).startswith("b.jsonl line 2: ")
    assert len(str(err.value)) > len("b.jsonl line 2: ")  # a reason follows


def test_record_the_model_rejects_names_file_and_line(tmp_path):
    _write(tmp_path, "a.jsonl", '{"id": "x", "n": 1}\n{"id": "y", "n": "lots"}\n')
    with pytest.raises(ValueError) as err:
        block.load_jsonl_dir(tmp_path, Row)
    assert str(err.value).startswith("a.jsonl line 2: ")
    assert "n" in str(err.value)[len("a.jsonl line 2: ") :]


def test_line_numbers_count_blank_lines(tmp_path):
    _write(tmp_path, "a.jsonl", '{"id": "x", "n": 1}\n\n   \n{"id": "y"}\n')
    with pytest.raises(ValueError) as err:
        block.load_jsonl_dir(tmp_path, Row)
    assert str(err.value).startswith("a.jsonl line 4: ")


def test_line_numbers_count_from_one_after_bom(tmp_path):
    (tmp_path / "a.jsonl").write_bytes("\ufeff{oops\n".encode("utf-8"))
    with pytest.raises(ValueError) as err:
        block.load_jsonl_dir(tmp_path, Row)
    assert str(err.value).startswith("a.jsonl line 1: ")


# Failure mode: not valid UTF-8 -> ValueError "<file name>: "


def test_invalid_utf8_raises_value_error_naming_file(tmp_path):
    (tmp_path / "a.jsonl").write_bytes(b'{"id": "\xff\xfe", "n": 1}\n')
    with pytest.raises(ValueError) as err:
        block.load_jsonl_dir(tmp_path, Row)
    assert not isinstance(err.value, UnicodeDecodeError)
    assert str(err.value).startswith("a.jsonl: ")


# Failure mode: repeated id_field values -> ValueError naming each, sorted


def test_duplicate_id_in_one_file_raises(tmp_path):
    _write(tmp_path, "a.jsonl", '{"id": "x", "n": 1}\n{"id": "x", "n": 2}\n')
    with pytest.raises(ValueError, match="x"):
        block.load_jsonl_dir(tmp_path, Row)


def test_duplicate_ids_across_files_all_named_sorted(tmp_path):
    _write(tmp_path, "a.jsonl", '{"id": "zeta", "n": 1}\n{"id": "alpha", "n": 2}\n')
    _write(
        tmp_path,
        "b.jsonl",
        '{"id": "alpha", "n": 3}\n{"id": "solo", "n": 4}\n{"id": "zeta", "n": 5}\n',
    )
    with pytest.raises(ValueError) as err:
        block.load_jsonl_dir(tmp_path, Row)
    msg = str(err.value)
    assert "alpha" in msg and "zeta" in msg
    assert msg.index("alpha") < msg.index("zeta")
    assert "solo" not in msg


def test_id_field_none_allows_repeats(tmp_path):
    _write(tmp_path, "a.jsonl", '{"id": "x", "n": 1}\n{"id": "x", "n": 2}\n')
    rows = block.load_jsonl_dir(tmp_path, Row, id_field=None)
    assert [r.n for r in rows] == [1, 2]


def test_custom_id_field_is_checked_instead_of_id(tmp_path):
    _write(tmp_path, "a.jsonl", '{"id": "x", "n": 1}\n{"id": "x", "n": 2}\n')
    assert len(block.load_jsonl_dir(tmp_path, Row, id_field="n")) == 2

    _write(tmp_path, "b.jsonl", '{"id": "y", "n": 7}\n{"id": "z", "n": 7}\n')
    with pytest.raises(ValueError, match="7"):
        block.load_jsonl_dir(tmp_path, Row, id_field="n")


# Failure mode: id_field the model doesn't have


def test_unknown_id_field_raises_has_no_field(tmp_path):
    _write(tmp_path, "a.jsonl", '{"id": "x", "n": 1}\n')
    with pytest.raises(ValueError, match="has no field"):
        block.load_jsonl_dir(tmp_path, Row, id_field="slug")


# Failure mode: no records at all


def test_no_jsonl_files_raises_no_records_found(tmp_path):
    _write(tmp_path, "notes.txt", "hello\n")
    with pytest.raises(ValueError, match="no records found"):
        block.load_jsonl_dir(tmp_path, Row)


def test_empty_folder_raises_no_records_found(tmp_path):
    with pytest.raises(ValueError, match="no records found"):
        block.load_jsonl_dir(tmp_path, Row)


def test_only_blank_lines_raises_no_records_found(tmp_path):
    _write(tmp_path, "a.jsonl", "\n   \n\n")
    _write(tmp_path, "b.jsonl", "")
    with pytest.raises(ValueError, match="no records found"):
        block.load_jsonl_dir(tmp_path, Row)


# Failure mode: folder missing or a file


def test_missing_folder_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        block.load_jsonl_dir(tmp_path / "nope", Row)


def test_folder_that_is_a_file_raises_file_not_found(tmp_path):
    path = _write(tmp_path, "a.jsonl", '{"id": "x", "n": 1}\n')
    with pytest.raises(FileNotFoundError):
        block.load_jsonl_dir(path, Row)


# Lines are split on "\n" only (like an editor); CRLF files work too


@pytest.mark.parametrize("sep", [" ", "\u0085", " "])
def test_unicode_line_separators_inside_strings_stay_one_record(tmp_path, sep):
    good = json.dumps({"id": f"a{sep}b", "n": 1}, ensure_ascii=False)
    assert sep in good  # written raw, not escaped
    text = good + "\n" + json.dumps({"id": "c", "n": 2}) + "\n{bad\n"
    _write(tmp_path, "a.jsonl", text)
    with pytest.raises(ValueError) as err:
        block.load_jsonl_dir(tmp_path, Row)
    assert str(err.value).startswith("a.jsonl line 3: ")

    _write(tmp_path, "a.jsonl", good + "\n")
    assert _ids(block.load_jsonl_dir(tmp_path, Row)) == [f"a{sep}b"]


def test_crlf_file_loads_and_counts_lines(tmp_path):
    path = tmp_path / "a.jsonl"
    path.write_bytes(b'{"id": "x", "n": 1}\r\n\r\n{"id": "y", "n": 2}\r\n')
    assert _ids(block.load_jsonl_dir(tmp_path, Row)) == ["x", "y"]
    path.write_bytes(b'{"id": "x", "n": 1}\r\n\r\n{bad\r\n')
    with pytest.raises(ValueError) as err:
        block.load_jsonl_dir(tmp_path, Row)
    assert str(err.value).startswith("a.jsonl line 3: ")


def test_empty_folder_with_unknown_id_field_says_no_records_found(tmp_path):
    """SPEC: the id_field check happens on the first record, so none = no records."""
    with pytest.raises(ValueError, match="no records found"):
        block.load_jsonl_dir(tmp_path, Row, id_field="slug")


# Input `what`: the plural word used in the "no ... found" message


def test_what_defaults_to_records_in_message(tmp_path):
    with pytest.raises(ValueError, match="no records found"):
        block.load_jsonl_dir(tmp_path, Row)


def test_what_cards_gives_no_cards_found(tmp_path):
    with pytest.raises(ValueError) as err:
        block.load_jsonl_dir(tmp_path, Row, what="cards")
    assert "no cards found" in str(err.value)
    assert "no records found" not in str(err.value)


def test_what_does_not_change_loaded_records(tmp_path):
    _write(tmp_path, "a.jsonl", '{"id": "x", "n": 1}\n')
    assert _ids(block.load_jsonl_dir(tmp_path, Row, what="cards")) == ["x"]


# Failure mode: unhashable id_field values -> ValueError "hashable", not TypeError


class Tagged(BaseModel):
    id: str
    tags: list[str]
    meta: dict[str, int]


@pytest.mark.parametrize("field", ["tags", "meta"])
def test_unhashable_id_field_raises_value_error_not_type_error(tmp_path, field):
    _write(
        tmp_path,
        "a.jsonl",
        '{"id": "x", "tags": ["a"], "meta": {"k": 1}}\n'
        '{"id": "y", "tags": ["b"], "meta": {"k": 2}}\n',
    )
    with pytest.raises(ValueError, match="hashable") as err:
        block.load_jsonl_dir(tmp_path, Tagged, id_field=field)
    assert not isinstance(err.value, TypeError)
