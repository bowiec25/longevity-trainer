# Block: `source_text`

> **In plain words:** Turn a pinned source (PDF, HTML page or JATS XML) into plain-text pages, so a quote can be checked in any format.

## Goal
Turn a pinned source (PDF, HTML page or JATS XML) into plain-text pages, so a quote can be checked in any format.

It exists because the quote check (`receipts`) only read PDFs, but most open sources are web pages (WHO) or journal XML from Europe PMC (findings in `docs/SOURCE_FORMATS.md`). The card writer (M3) also needs the plain text to read. A "page" is a real page for a PDF; a web page or an article is **one** page.

**Not in scope:** downloading or pinning (`receipts.ensure_source`); matching quotes (`receipts.find_quote`, which reduces text to keys); judging whether a source is trustworthy.

## Kind
**script.** Getting text out of a file is mechanical and code can check it (a known sentence is found or not).

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `path` | `Path` | The downloaded document |
| `format` | `str` | `"pdf"`, `"html"` or `"jats-xml"` (the `format` field of a source record; a record with any other format is rejected when it's loaded) |

**How it's called** (importable from `quizkit.blocks.source_text`):
```python
pages = text_pages(Path("data/raw/pearl-2025.xml"), "jats-xml")  # list[str]
```

## Outputs
| Output | Type | Plain meaning |
|---|---|---|
| `text_pages` | `list[str]` | Plain text, one string per page, in order (index 0 = page 1). `pdf`: one per PDF page (an empty page gives `""`). `html` and `jats-xml`: exactly one string |
| `FORMATS` | `tuple[str, ...]` | The formats it reads: `("pdf", "html", "jats-xml")` |

What goes into the text:
- **html:** all visible text. Never the contents of `<head>` (so not the tab title), `<script>`, `<style>`, `<noscript>`, `<template>`, `<svg>`, or an element with the `hidden` attribute or `style="display:none"`. An unclosed hidden element stops hiding when the element it sits in is closed (a stray `<noscript>` can't hide the rest of the page). HTML entities are decoded (`&amp;` → `&`, `&alpha;` → `α`). The page is decoded with the charset its `<meta>` declares (else UTF-8).
- **jats-xml:** the article title, the abstract(s), the body and a top-level `<floats-group>` (where some publishers put figures and tables), including captions. An article inside a wrapper (`<pmc-articleset>`, OAI-PMH) is found. Also left out: author/funding notes (`<fn-group>`), supplementary-file labels, copyright lines (`<permissions>`) and the machine form of formulas (TeX, MathML annotations). A `<break/>` separates words. Not the metadata (journal ids, author list, affiliations), not `<back>`, and never a reference list (`<ref-list>`) **wherever it sits** (some publishers, e.g. PEARL's, put it inside `<body>`), so a quote can't be "found" in someone else's paper title. Section titles (`<sec><title>`) are kept.
- **Both:** text from separate elements is joined with a space, so words from neighbouring paragraphs or table cells never run together. Text inside one element (e.g. `rapa<italic>my</italic>cin`) is kept as written. Runs of whitespace become one space; the result is stripped.

The receipts block uses it: a source record gains `format` (default `"pdf"`, so old records still work), and `check_all` checks quotes against `text_pages` for that format. A receipt quoting an html or jats-xml source has `page` 1.

## Tools
- `pypdf` (PDF pages, as `receipts` already used)
- Python's standard library only for the rest: `html.parser.HTMLParser`, `xml.etree.ElementTree` (no new dependency). ElementTree doesn't fetch external DTDs or entities, so a document can't make it go online.

## Failure modes
| Situation | What it does |
|---|---|
| `path` doesn't exist | Raises `FileNotFoundError` |
| An unknown `format` (e.g. `"docx"`) | Raises `ValueError` naming the format and listing `FORMATS` |
| Broken XML | Raises `ValueError` ("not valid XML: …"); `check_all` reports the source as unusable, one line per receipt, no traceback |
| XML that isn't a JATS article (no `<article>`, or one with no `<body>` and no `<abstract>`) | Raises `ValueError` ("no article text"); an empty result would make every quote "not found" for a confusing reason |
| HTML with no visible text | Returns `[""]` (one empty page) |
| A corrupt PDF | Whatever `pypdf` raises (as before; `check_all` reports "unreadable") |

## How to test
Automatic tests in `tests/blocks/test_source_text.py`, on small files written in the test (`tmp_path`):
- **html:** visible text kept; head/script/style/noscript/template/svg, `hidden` and `display:none` dropped; an unclosed `<noscript>` inside a `<p>` doesn't hide the next paragraph; a latin-1 page with a `<meta charset>` decodes accents; entities decoded; neighbouring paragraphs and table cells don't run together; whitespace collapsed; exactly one page
- **jats-xml:** title, abstract and body kept (incl. a caption, and one in a top-level `<floats-group>`); a wrapped article found; `<fn-group>`, `<supplementary-material>`, `<permissions>` and `<tex-math>` dropped; `<break/>` separates words; metadata, `<back>` and any `<ref-list>` (also one inside `<body>`) dropped; inline markup kept as one word; a DOCTYPE line pointing at a DTD doesn't break it; broken XML and a non-article raise `ValueError`
- **pdf:** one string per page (a tiny PDF made in the test, or skip if that's not possible)
- **Errors:** missing file, unknown format
- **Real sources** (skipped if `data/raw/` doesn't have them, as in CI): a known sentence from each of the 4 pinned sources is found by `receipts.find_quote` on the keys of its pages
- **receipts:** `Source` reads `format` (default `"pdf"`); `check_all` finds a quote in an html source and in a jats-xml source (page 1), with a fake fetch
- **Contract test:** folder parts exist and `BLOCK_SPEC` matches this SPEC
