# Block: `jsonl_loader`

> **In plain words:** Load every record from a folder of .jsonl files into a pydantic model, failing loudly (file and line) on any bad record or repeated id.

## Goal
Load every record from a folder of .jsonl files into a pydantic model, failing loudly (file and line) on any bad record or repeated id.

It exists because every quiz keeps its content as "one JSON record per line, several files in a folder" (cards, sources, sentences), and each needs the same care: a bad line must name its file and line, repeats must be caught, an empty folder is a bug. The quiz passes its own model (e.g. `LongevityCard`); this block knows nothing about what's inside.

**Not in scope:** what makes a record valid (the model's job); writing files.

## Kind
**script.** Code can check the output: each line parses into the model or it doesn't (ADR 0002).

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `folder` | `Path` | A folder of `*.jsonl` files. Only `*.jsonl` files directly in it are read, in name order; other files and subfolders are ignored |
| `model` | a pydantic `BaseModel` class | What each line becomes, e.g. `LongevityCard` |
| `id_field` | `str \| None` | The field that must be unique across all files (default `"id"`). `None` = no uniqueness check |
| `what` | `str` | The plural word for the records in messages (default `"records"`; a quiz passes `"cards"`) |

Each file is read as UTF-8; a UTF-8 byte-order mark at the start (common from Windows editors) is ignored. Blank (or spaces-only) lines are skipped but still counted in line numbers, like an editor.

**How it's called:**
```python
from quizkit.blocks.jsonl_loader import load_jsonl_dir

cards = load_jsonl_dir(Path("data/cards"), LongevityCard)  # unique "id"
rows = load_jsonl_dir(Path("data/x"), Row, id_field=None)  # no id check
```

## Outputs
| Output | Type | Plain meaning |
|---|---|---|
| `load_jsonl_dir` | `list[model]` | Every record, in file-name order then line order |

Nothing is written.

## Tools
- pydantic (`model.model_validate_json`)
- `pathlib`

## Failure modes
Errors name the file by its bare name (`cards.jsonl`, not the full path). Loading stops at the first bad line or file; the repeat check runs only after every line loaded. Use lower-case `.jsonl` names (on Linux, `A.JSONL` isn't read).

| Situation | What it does |
|---|---|
| A line that isn't valid JSON, or that the model rejects | **Raises `ValueError`** whose message starts `"<file name> line <n>: "`, followed by the reason |
| A file that isn't valid UTF-8 | **Raises `ValueError`** whose message starts `"<file name>: "` (never a bare `UnicodeDecodeError`) |
| Two records with the same `id_field` value (one file or across files) | **Raises `ValueError`** naming every repeated value, sorted |
| `id_field` names a field the model doesn't have | **Raises `ValueError`** ("… has no field …"), checked after loading (an empty folder gives "no records found" first) |
| No records at all (no `.jsonl` files, or only blank lines) | **Raises `ValueError`** containing "no <what> found" (default "no records found") |
| `id_field` values that can't be compared for repeats (a list or dict) | **Raises `ValueError`** ("… must be hashable …"), never a bare `TypeError` |
| The folder doesn't exist (or is a file) | **Raises `FileNotFoundError`** |

## How to test
Automatic tests in `tests/blocks/test_jsonl_loader.py`, with a tiny model defined in the test (e.g. `id: str`, `n: int`) and files in `tmp_path`. No network.
- **Loads:** two files in name order, lines in order; blank and spaces-only lines skipped; non-`.jsonl` files and subfolders ignored; a BOM at the start of a file is fine
- **Line numbers** count blank lines
- **Each failure mode** above, checking the message starts with the file name (and line where stated)
- **`id_field=None`** allows repeats; a custom `id_field` (e.g. `"n"`) is checked instead of `"id"`
- **Contract test:** folder parts exist and `BLOCK_SPEC` matches this SPEC

Manual check: none.
