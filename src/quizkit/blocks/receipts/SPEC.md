# Block: `receipts`

> **In plain words:** Check that a quote really appears, word for word, in a pinned source document, and on which page.

## Goal
Check that a quote really appears, word for word, in a pinned source document, and on which page.

It exists so a quiz can prove every answer: each card carries a **receipt** (a source id, a word-for-word quote, the page), and this block finds the quote in the real document. It is generic: any quiz with sourced cards can use it (it knows nothing about longevity). A source is **pinned**: its URL, size and SHA-256 are recorded, so the document checked is exactly the one the quote came from.

PDF text is messy: ligatures (`ﬁ`), words split by a hyphen at a line end (`macroautoph-` / `agy`), curly quotes, accents stored as a letter plus a separate mark, line breaks and page furniture. So both the quote and the page are reduced to a **key**: lower-case ASCII letters and digits, plus words for what science quotes turn on: Greek letters, with or without accents (`α` and `ά` → `alpha`), `≥ ≤ < > % ± =`, and a decimal point between digits (`1.5` → `1dot5`, so it differs from `15`). A changed, added or removed word breaks the match. **Known limit:** spaces are dropped, so a re-split word (`a part` vs `apart`) still matches; a minus sign vs a hyphen isn't told apart either. Rare in quotes; the fact-auditor (M3) reads the meaning.

**Not in scope:** whether the quote supports the card's answer (that needs judgment: the fact-auditor agent, M3); finding sources (M2).

## Kind
**script.** Code can check the output: a quote's key is either inside a page's key or it isn't. Free, instant, no judgment (ADR 0002).

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `source_file` | `Path` | A pinned source record, JSON: `id`, `title`, `url` (https), `size` (bytes), `sha256` (64 hex characters), `local_path` (where the document is kept, relative to the project root). Extra fields (authors, doi, licence note…) are allowed and kept out of the way |
| `root` | `Path` | The project root that `local_path` is relative to |
| `fetch` | `Callable[[str], bytes]` | Downloads a URL (default: a real download with a generic User-Agent). Tests pass a fake |
| `pdf_path` | `Path` | A downloaded PDF to read |
| `quote` | `str` | The quote to find |
| `pages` | `list[str]` | A document's page keys (from `page_keys`), index 0 = page 1 |
| `receipts` | `list[tuple[str, Receipt]]` | What to check: (a label such as the card id, its receipt) |
| `pages_by_source` | `dict[str, list[str]]` | Page keys for each source id |
| `sources_dir` | `Path` | The folder of source records, one `<source id>.json` per source |

**How it's called** (all importable from `quizkit.blocks.receipts`):
```python
to_key(text) -> str                       # "Macroautoph-\nagy" -> "macroautophagy"
Receipt(source="id", quote="...", page=9) # pydantic, frozen
Source                                    # pydantic, frozen; .path(root) -> Path
load_source(source_file) -> Source
ensure_source(source, root, fetch=...) -> Path   # download if missing; always verify
page_keys(pdf_path) -> list[str]
find_quote(quote, pages) -> int | None    # 1-based page, or None
check_receipts(receipts, pages_by_source) -> list[str]   # problems; [] = all good
check_all(receipts, sources_dir, root, fetch=...) -> list[str]  # load + fetch + read + check
```

## Outputs
| Output | Type | Plain meaning |
|---|---|---|
| `to_key` | `str` | The comparison key described in Goal: ligatures become letters, accents are dropped (`López` → `lopez`), Greek letters and `≥ ≤ < > % ± =` become words (`alpha`, `ge`, `le`, `lt`, `gt`, `pct`, `pm`, `eq`), a `.`/`,`/`·` between two digits becomes `dot`; spaces, hyphens, quotes and other punctuation disappear |
| `Receipt` | pydantic model | `source` (non-empty), `quote` (its **key** has at least 20 characters, so a quote can't be a word or dots that match anywhere), `page` (≥ 1). Frozen; unknown fields rejected |
| `Source` | pydantic model | The six fields above; extra fields in the record (authors, doi…) are **ignored** (not stored). `path(root)` = `root / local_path`, and raises `ValueError` if that resolves outside `root` (a second guard behind the `local_path` rule) |
| `ensure_source` | `Path` | Where the verified document now is (`source.path(root)`, the same path whether it downloaded or a correct copy was already there). Downloads only if it is missing or wrong |
| `page_keys` | `list[str]` | One key per PDF page, in order. A page with no text gives `""` |
| `find_quote` | `int \| None` | The first page (1-based) whose key contains the quote's key; `None` if none does |
| `check_receipts` | `list[str]` | One line per bad receipt, in the order given: `"<label>: quote not found in <source>"`, `"<label>: quote is on page <found>, receipt says <page>"`, or `"<label>: unknown source <source>"`. Empty list = every quote found on its page |

| `check_all` | `list[str]` | Every receipt checked: each source record is loaded from `sources_dir`, fetched if needed, read once. Lines as `check_receipts`, plus, for every receipt citing a source that can't be used, one line `"<label>: <reason>"` (no record file: `"no source record <id>.json"`; a record whose `id` differs from its file name, a bad record, a failed download, an unreadable PDF: `"source <id> unusable (...)"` or `"... unreadable (...)"`). `<id>` is the source id the receipts cite (the record's file name). Never a traceback for a bad source, including a record that isn't valid JSON or fails validation |

Nothing is written except the downloaded document (at `source.path(root)`, via `quizkit.download.download_verified`).

## Tools
- `unicodedata` (NFKD) for keys
- `pypdf` (`PdfReader`) for page text; its font warnings are silenced (they are noise here)
- `quizkit.download.download_verified` for the pinned download (size + SHA-256)
- `quizkit.download.http_get` as the default `fetch` (it sends the generic User-Agent `quizkit`, never personal details; some repositories refuse Python's default)
- pydantic for `Receipt` and `Source`

## Failure modes
| Situation | What it does |
|---|---|
| A quote whose key is empty (only punctuation or spaces) | `find_quote` returns `None` (an empty key would match every page) |
| A quote that spans a page break | Not found (`None`): pages are checked one at a time, so pick a quote within one page |
| The quote appears on several pages | The first page is returned |
| `check_receipts` with a receipt whose source isn't in `pages_by_source` | A problem line `"<label>: unknown source <source>"`, not a crash |
| A source record that is missing a field, has an empty or spaces-only `id`, `title` or `local_path`, a non-https URL, a SHA-256 that isn't 64 **lower-case** hex characters, or a size < 1 | **Raises** pydantic `ValidationError` from `load_source` |
| A `local_path` that is absolute, has a Windows drive (`C:/x`, `C:x`) or is a network path (`\server\share`), or has a `..` path segment (`a/../b`; a name like `file..pdf` is fine) (it could escape `root`) | **Raises** `ValidationError`: a record can't make the download land outside the project |
| The source record file isn't valid JSON | **Raises** `json.JSONDecodeError` (a `ValueError`) |
| Trying to change a `Receipt` or `Source` after it is made | **Raises** `ValidationError` (both are frozen) |
| The source record file doesn't exist | **Raises** `FileNotFoundError` |
| The document is missing locally | `ensure_source` downloads it |
| The local copy is there but wrong (size or SHA-256) | `ensure_source` downloads it again |
| The download fails, or its size or SHA-256 doesn't match the pin | **Raises** `quizkit.download.DownloadError`; the bad download is not saved (an older wrong copy, if any, is left as it was and will be replaced on the next good download) |
| The PDF exists but is corrupt or not a PDF | **Raises** pypdf's error (`pypdf.errors.PdfReadError` or similar), not swallowed: a broken source must be loud |
| `pdf_path` doesn't exist | **Raises** `FileNotFoundError` |
| A `Receipt` whose quote's key has < 20 characters (e.g. `"a . . . . . . . . . b"`), an empty or spaces-only source, page < 1, or an unknown field | **Raises** `ValidationError` |

## How to test
Automatic tests in `tests/blocks/test_receipts.py`, with **no network** (a fake `fetch`) and **no real PDF**: page keys are built from small strings, and a tiny PDF for `page_keys` is made in the test (e.g. with `pypdf` writing blank pages, or a minimal hand-written PDF).
- **Keys:** ligature `ﬁ` → `fi`; `"macroautoph-\nagy"` = `"macroautophagy"`; curly vs straight quotes match; split accents (`"López"`) = `"López"` = `"lopez"`; case and spaces ignored
- **find_quote:** returns the right 1-based page; the first page when on several; `None` when one word is changed, added or removed; `None` for an empty-key quote
- **check_receipts:** all good → `[]`; wrong page → the "is on page" line; missing quote → the "not found" line; unknown source → the "unknown source" line; order kept
- **Receipt / Source validation:** each rejected case in Failure modes
- **ensure_source:** downloads when missing (fake fetch called once); doesn't call fetch when a correct copy is there; re-downloads a wrong copy; wrong size or SHA from fetch → `DownloadError` and no file saved
- **page_keys:** a blank page gives `""`; the number of keys = the number of pages; missing file → `FileNotFoundError`
- **Contract test:** folder parts exist and `BLOCK_SPEC` matches this SPEC

Manual check: `uv run longevity check-receipts` against the real pinned review (CI skips it: no download there; see FUTURE.md).
