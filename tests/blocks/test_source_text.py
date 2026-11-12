"""Tests for the source_text block, written from its SPEC.md (test-first, no network)."""

import hashlib
import json
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import quizkit.blocks.source_text as block
from quizkit.blocks.base import missing_spec_sections, spec_section
from quizkit.blocks.receipts import Receipt, check_all, find_quote, load_source, to_key

SPEC_MD = Path(block.__file__).parent / "SPEC.md"
REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "data" / "raw"


def text_pages(path: Path, fmt: str) -> list[str]:
    """Call through the module so a missing function fails only its own tests."""
    return block.text_pages(path, fmt)


# --- Contract test -----------------------------------------------------------


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "source_text"
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


def test_formats_constant():
    assert block.FORMATS == ("pdf", "html", "jats-xml")


# --- html ----------------------------------------------------------------------


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


HTML = """<!DOCTYPE html>
<html><head><title>Physical activity</title>
<style>body { color: red; } .hidden-style-text {}</style>
<script>var secretScript = "do not keep";</script>
</head><body>
<noscript>Enable JavaScript noscriptword</noscript>
<template><p>templateword inside</p></template>
<svg><text>svgword label</text></svg>
<h1>Key facts</h1>
<p>Adults should do at least 150 minutes of activity.</p><p>Second paragraph here.</p>
<table><tr><td>cellone</td><td>celltwo</td></tr></table>
<p>Fish &amp; chips, &alpha;-klotho, 20&ndash;30%</p>
<p>spaced      out
   words</p>
</body></html>
"""


@pytest.fixture
def html_pages(tmp_path) -> list[str]:
    return text_pages(write(tmp_path, "page.html", HTML), "html")


def test_html_is_exactly_one_page(html_pages):
    assert len(html_pages) == 1


def test_html_keeps_visible_text(html_pages):
    assert "Adults should do at least 150 minutes of activity." in html_pages[0]
    assert "Key facts" in html_pages[0]


@pytest.mark.parametrize(
    "hidden",
    ["color: red", "secretScript", "noscriptword", "templateword", "svgword"],
)
def test_html_drops_hidden_elements(html_pages, hidden):
    assert hidden not in html_pages[0]


def test_html_decodes_entities(html_pages):
    page = html_pages[0]
    assert "Fish & chips" in page
    assert "α-klotho" in page
    assert "20–30%" in page
    assert "&amp;" not in page and "&alpha;" not in page


def test_html_neighbouring_elements_do_not_run_together(html_pages):
    page = html_pages[0]
    assert "activity. Second paragraph" in page
    assert "cellone celltwo" in page


def test_html_whitespace_collapsed_and_stripped(html_pages):
    page = html_pages[0]
    assert "spaced out words" in page
    assert "  " not in page and "\n" not in page
    assert page == page.strip()


def test_html_with_no_visible_text_gives_one_empty_page(tmp_path):
    path = write(tmp_path, "empty.html", "<html><head><script>x()</script></head>"
                 "<body>   </body></html>")  # fmt: skip
    assert text_pages(path, "html") == [""]


# --- jats-xml ------------------------------------------------------------------

JATS = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE article PUBLIC "-//NLM//DTD JATS (Z39.96) Journal Archiving and Interchange DTD v1.2 20190208//EN" "https://jats.nlm.nih.gov/archiving/1.2/JATS-archivearticle1-2.dtd">
<article xmlns:xlink="http://www.w3.org/1999/xlink">
<front>
<journal-meta><journal-id journal-id-type="nlm-ta">JournalIdXyz</journal-id></journal-meta>
<article-meta>
<title-group><article-title>Rapamycin and healthspan in people</article-title></title-group>
<contrib-group><contrib><name><surname>Authorsurname</surname><given-names>Ann</given-names></name></contrib></contrib-group>
<aff>Affiliationplace University</aff>
<abstract><p>Abstract sentence about dosing.</p></abstract>
</article-meta>
</front>
<body>
<sec><title>Introduction</title>
<p>Body paragraph one ends here.</p><p>Body paragraph two starts here.</p>
<p>We gave rapa<italic>my</italic>cin weekly.</p>
<fig><caption><p>Figure caption text shown.</p></caption></fig>
<table-wrap><caption><p>Table caption text shown.</p></caption>
<table><tr><td>cellone</td><td>celltwo</td></tr></table></table-wrap>
<p>loose    spaced
   words</p>
</sec>
</body>
<back><ref-list><ref><mixed-citation>Someone else wrote a referencedtitle paper.</mixed-citation></ref></ref-list></back>
</article>
"""


@pytest.fixture
def jats_pages(tmp_path) -> list[str]:
    return text_pages(write(tmp_path, "article.xml", JATS), "jats-xml")


def test_jats_is_exactly_one_page(jats_pages):
    assert len(jats_pages) == 1


@pytest.mark.parametrize(
    "kept",
    [
        "Rapamycin and healthspan in people",
        "Abstract sentence about dosing.",
        "Body paragraph one ends here.",
        "Figure caption text shown.",
        "Table caption text shown.",
    ],
)
def test_jats_keeps_title_abstract_body_and_captions(jats_pages, kept):
    assert kept in jats_pages[0]


@pytest.mark.parametrize(
    "dropped", ["JournalIdXyz", "Authorsurname", "Affiliationplace", "referencedtitle"]
)
def test_jats_drops_metadata_and_references(jats_pages, dropped):
    assert dropped not in jats_pages[0]


def test_jats_inline_markup_kept_as_one_word(jats_pages):
    assert "rapamycin weekly" in jats_pages[0]


def test_jats_neighbouring_elements_do_not_run_together(jats_pages):
    page = jats_pages[0]
    assert "ends here. Body paragraph two" in page
    assert "cellone celltwo" in page


def test_jats_whitespace_collapsed_and_stripped(jats_pages):
    page = jats_pages[0]
    assert "loose spaced words" in page
    assert "  " not in page and "\n" not in page
    assert page == page.strip()


def test_jats_broken_xml_raises_value_error(tmp_path):
    path = write(tmp_path, "broken.xml", "<article><body><p>unclosed</body>")
    with pytest.raises(ValueError, match="not valid XML"):
        text_pages(path, "jats-xml")


def test_jats_non_article_raises_value_error(tmp_path):
    path = write(tmp_path, "other.xml", "<feed><entry>Not an article</entry></feed>")
    with pytest.raises(ValueError, match="no article text"):
        text_pages(path, "jats-xml")


def test_jats_abstract_only_is_enough(tmp_path):
    xml = "<article><front><article-meta><abstract><p>Only an abstract here."
    xml += "</p></abstract></article-meta></front></article>"
    pages = text_pages(write(tmp_path, "abs.xml", xml), "jats-xml")
    assert "Only an abstract here." in pages[0]


# --- pdf -----------------------------------------------------------------------


def make_text_pdf(path: Path, texts: list[str]) -> Path:
    """A tiny PDF with one line of Helvetica text per page ("" = blank page)."""
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=400, height=200)
        if not text:
            continue
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): writer._add_object(font)}
                )
            }
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as f:
        writer.write(f)
    return path


def test_pdf_one_string_per_page_in_order(tmp_path):
    pdf = make_text_pdf(
        tmp_path / "t.pdf", ["Hallmarks of Ageing", "", "Rapamycin inhibits mTOR"]
    )
    assert "Rapamycin" in PdfReader(pdf).pages[2].extract_text()  # helper sanity
    pages = text_pages(pdf, "pdf")
    assert len(pages) == 3
    assert "Hallmarks of Ageing" in pages[0]
    assert pages[1] == ""
    assert "Rapamycin inhibits mTOR" in pages[2]


def test_corrupt_pdf_raises(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"this is not a pdf at all")
    with pytest.raises(Exception) as excinfo:
        text_pages(bad, "pdf")
    assert not isinstance(excinfo.value, (FileNotFoundError, AttributeError))


# --- Errors --------------------------------------------------------------------


@pytest.mark.parametrize("fmt", ["pdf", "html", "jats-xml"])
def test_missing_file_raises_file_not_found(tmp_path, fmt):
    with pytest.raises(FileNotFoundError):
        text_pages(tmp_path / "nope", fmt)


def test_unknown_format_raises_value_error_naming_it_and_formats(tmp_path):
    path = write(tmp_path, "doc.docx", "whatever")
    with pytest.raises(ValueError) as excinfo:
        text_pages(path, "docx")
    message = str(excinfo.value)
    assert "docx" in message
    for fmt in ("pdf", "html", "jats-xml"):
        assert fmt in message


# --- Real sources (skipped when data/raw/ is absent, as in CI) -----------------

REAL = [
    (
        "hallmarks-of-aging-2023.pdf",
        "pdf",
        (
            "Aging is driven by hallmarks fulfilling the following three premises: "
            "(1) their age-associated manifestation, (2) the acceleration of aging by "
            "experimentally accentuating them, and (3) the opportunity to decelerate, "
            "stop, or reverse aging by therapeutic interventions on them."
        ),
    ),
    (
        "measuring-biological-aging-2020.xml",
        "jats-xml",
        (
            "Cellular senescence is a stress response mechanism characterized by "
            "replication arrest and complex changes in morphology, chromatin "
            "organization, secretome, and expression of typical protein biomarkers"
        ),
    ),
    (
        "pearl-2025.xml",
        "jats-xml",
        (
            "The widespread adoption of rapamycin as a gerotherapeutic has historically "
            "been limited by concerns regarding its known impact on immunosuppression, "
            "hyperlipidemia, and hyperglycemia"
        ),
    ),
    (
        "who-physical-activity.html",
        "html",
        (
            "People who are insufficiently active have a 20–30% increased risk of death "
            "compared to people who are sufficiently active."
        ),
    ),
]


def real_keys(name: str, fmt: str) -> list[str]:
    path = RAW / name
    if not path.exists():
        pytest.skip(f"{name} not in data/raw/ (gitignored)")
    return [to_key(p) for p in text_pages(path, fmt)]


@pytest.mark.parametrize("name, fmt, quote", REAL, ids=[r[0] for r in REAL])
def test_real_source_known_sentence_is_found(name, fmt, quote):
    assert find_quote(quote, real_keys(name, fmt)) is not None


def test_real_jats_reference_list_title_not_found():
    """A cited paper's title (only in pearl's <ref-list>) must not count as found.

    Note: in this Europe PMC file the <ref-list> sits inside <body>, not <back>.
    """
    keys = real_keys("pearl-2025.xml", "jats-xml")
    title = (
        "Healthy living is the best revenge: findings from the European "
        "Prospective Investigation Into Cancer and Nutrition-Potsdam study"
    )
    assert find_quote(title, keys) is None


# --- receipts integration ------------------------------------------------------


def source_record(**overrides) -> dict:
    data = b"%PDF-1.4 pretend"
    record = {
        "id": "rev",
        "title": "A review",
        "url": "https://example.org/rev.pdf",
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "local_path": "sources/rev.pdf",
    }
    record.update(overrides)
    return record


def test_source_format_defaults_to_pdf(tmp_path):
    path = write(tmp_path, "rev.json", json.dumps(source_record()))
    assert load_source(path).format == "pdf"


@pytest.mark.parametrize("fmt", ["pdf", "html", "jats-xml"])
def test_source_reads_format(tmp_path, fmt):
    path = write(tmp_path, "rev.json", json.dumps(source_record(format=fmt)))
    assert load_source(path).format == fmt


class UrlFetch:
    """Fake fetch: url -> bytes; records calls."""

    def __init__(self, by_url: dict):
        self.by_url = by_url
        self.calls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        return self.by_url[url]


def add_source(sources_dir: Path, sid: str, data: bytes, fmt: str, ext: str) -> str:
    """Write <sid>.json pinning `data` with the given format; return its URL."""
    sources_dir.mkdir(exist_ok=True)
    url = f"https://example.org/{sid}.{ext}"
    record = {
        "id": sid,
        "title": f"Title {sid}",
        "url": url,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "local_path": f"docs/{sid}.{ext}",
        "format": fmt,
    }
    (sources_dir / f"{sid}.json").write_text(json.dumps(record), encoding="utf-8")
    return url


HTML_QUOTE = "Adults should do at least 150 minutes of activity"
JATS_QUOTE = "Body paragraph one ends here. Body paragraph two"


@pytest.mark.parametrize(
    "fmt, ext, doc, quote",
    [("html", "html", HTML, HTML_QUOTE), ("jats-xml", "xml", JATS, JATS_QUOTE)],
)
def test_check_all_finds_quote_on_page_1(tmp_path, fmt, ext, doc, quote):
    data = doc.encode("utf-8")
    sdir = tmp_path / "sources"
    url = add_source(sdir, "src", data, fmt, ext)
    fetch = UrlFetch({url: data})
    receipts = [("c1", Receipt(source="src", quote=quote, page=1))]
    assert check_all(receipts, sdir, tmp_path, fetch=fetch) == []


@pytest.mark.parametrize(
    "fmt, ext, doc, quote",
    [("html", "html", HTML, HTML_QUOTE), ("jats-xml", "xml", JATS, JATS_QUOTE)],
)
def test_check_all_wrong_page_for_one_page_source(tmp_path, fmt, ext, doc, quote):
    data = doc.encode("utf-8")
    sdir = tmp_path / "sources"
    url = add_source(sdir, "src", data, fmt, ext)
    receipts = [("c1", Receipt(source="src", quote=quote, page=2))]
    assert check_all(receipts, sdir, tmp_path, fetch=UrlFetch({url: data})) == [
        "c1: quote is on page 1, receipt says 2"
    ]


def test_check_all_hidden_html_text_is_not_found(tmp_path):
    data = HTML.encode("utf-8")
    sdir = tmp_path / "sources"
    url = add_source(sdir, "src", data, "html", "html")
    quote = 'var secretScript = "do not keep"'
    receipts = [("c1", Receipt(source="src", quote=quote, page=1))]
    assert check_all(receipts, sdir, tmp_path, fetch=UrlFetch({url: data})) == [
        "c1: quote not found in src"
    ]


def test_check_all_broken_xml_is_unusable_one_line_per_receipt(tmp_path):
    data = b"<article><body><p>unclosed</body>"
    sdir = tmp_path / "sources"
    url = add_source(sdir, "src", data, "jats-xml", "xml")
    receipts = [
        ("c1", Receipt(source="src", quote=JATS_QUOTE, page=1)),
        ("c2", Receipt(source="src", quote=JATS_QUOTE, page=1)),
    ]
    lines = check_all(receipts, sdir, tmp_path, fetch=UrlFetch({url: data}))
    assert len(lines) == 2
    for line, label in zip(lines, ["c1", "c2"]):
        assert line.startswith(f"{label}: ")
        assert "unusable" in line or "unreadable" in line


# --- html: more hidden-text rules ------------------------------------------------


def html_page(tmp_path: Path, body: str) -> str:
    return text_pages(write(tmp_path, "p.html", body), "html")[0]


def test_html_drops_head_title(tmp_path):
    page = html_page(
        tmp_path,
        "<html><head><title>TabTitle</title></head><body><p>Shown</p></body></html>",
    )
    assert "TabTitle" not in page
    assert "Shown" in page


def test_html_drops_element_with_hidden_attribute(tmp_path):
    page = html_page(tmp_path, "<body><div hidden>hiddenattrword</div><p>Shown</p>")
    assert "hiddenattrword" not in page
    assert "Shown" in page


def test_html_drops_display_none(tmp_path):
    page = html_page(
        tmp_path, '<body><div style="display:none">displaynoneword</div><p>Shown</p>'
    )
    assert "displaynoneword" not in page
    assert "Shown" in page


def test_html_unclosed_noscript_does_not_swallow_later_text(tmp_path):
    page = html_page(tmp_path, "<body><p>a<noscript>b</p><p>c visible</p></body>")
    assert "c visible" in page


def test_html_meta_charset_latin1_decoded(tmp_path):
    path = tmp_path / "latin.html"
    html = (
        '<html><head><meta charset="iso-8859-1"></head><body><p>café</p></body></html>'
    )
    path.write_bytes(html.encode("latin-1"))
    assert "café" in text_pages(path, "html")[0]


# --- jats-xml: more structure rules ------------------------------------------------


def jats_page(tmp_path: Path, xml: str) -> str:
    return text_pages(write(tmp_path, "a.xml", xml), "jats-xml")[0]


def test_jats_keeps_caption_in_top_level_floats_group(tmp_path):
    xml = (
        "<article><body><p>Body text.</p></body>"
        "<floats-group><fig><caption><p>Floating caption kept.</p></caption></fig>"
        "</floats-group></article>"
    )
    assert "Floating caption kept." in jats_page(tmp_path, xml)


def test_jats_reads_article_inside_pmc_articleset(tmp_path):
    xml = "<pmc-articleset><article><body><p>Wrapped body text.</p></body></article></pmc-articleset>"
    assert "Wrapped body text." in jats_page(tmp_path, xml)


@pytest.mark.parametrize(
    "element, word",
    [
        ("fn-group", "footnoteword"),
        ("supplementary-material", "supplword"),
        ("permissions", "licenceword"),
        ("tex-math", "texword"),
    ],
)
def test_jats_drops_non_prose_elements(tmp_path, element, word):
    xml = f"<article><body><p>Kept text.</p><{element}>{word}</{element}></body></article>"
    page = jats_page(tmp_path, xml)
    assert word not in page
    assert "Kept text." in page


def test_jats_break_becomes_space(tmp_path):
    assert "A B" in jats_page(
        tmp_path, "<article><body><p>A<break/>B</p></body></article>"
    )


def test_jats_without_article_element_raises_value_error(tmp_path):
    path = write(tmp_path, "x.xml", "<root><body><p>Some text</p></body></root>")
    with pytest.raises(ValueError):
        text_pages(path, "jats-xml")
