"""Tests for the receipts block, written from its SPEC.md (test-first, no network)."""

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import quizkit.blocks.receipts as block
from quizkit.blocks.base import missing_spec_sections, spec_section
from quizkit.blocks.receipts import (
    Receipt,
    Source,
    check_all,
    check_receipts,
    ensure_source,
    find_quote,
    load_source,
    page_keys,
    to_key,
)
from quizkit.download import DownloadError

SPEC_MD = Path(block.__file__).parent / "SPEC.md"


# --- Contract test -----------------------------------------------------------


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "receipts"
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


# --- Helpers -------------------------------------------------------------------

DOC = b"%PDF-1.4 pretend document bytes"
DOC_SHA = hashlib.sha256(DOC).hexdigest()


def source_record(**overrides) -> dict:
    record = {
        "id": "review2023",
        "title": "A review",
        "url": "https://example.org/review.pdf",
        "size": len(DOC),
        "sha256": DOC_SHA,
        "local_path": "sources/review.pdf",
    }
    record.update(overrides)
    return record


def write_record(tmp_path: Path, record: dict) -> Path:
    path = tmp_path / "source.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


class FakeFetch:
    def __init__(self, data: bytes = DOC):
        self.data = data
        self.calls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        return self.data


QUOTE = "autophagy declines with age in many tissues"


# --- to_key ----------------------------------------------------------------------


def test_key_turns_ligature_into_letters():
    assert to_key("ﬁbrosis") == "fibrosis"


def test_key_joins_word_split_by_line_end_hyphen():
    assert to_key("Macroautoph-\nagy") == "macroautophagy"
    assert to_key("macroautoph-\nagy") == to_key("macroautophagy")


def test_key_curly_and_straight_quotes_match():
    assert to_key("“the cell’s clock”") == to_key('"the cell\'s clock"')


def test_key_drops_accents_split_or_combined():
    split = "López"  # o + combining acute accent
    combined = "López"
    assert to_key(split) == to_key(combined) == "lopez"


def test_key_ignores_case_spaces_and_punctuation():
    assert to_key("  Hallmarks of Ageing, 2023! ") == "hallmarksofageing2023"


def test_key_keeps_only_lowercase_ascii_letters_and_digits():
    key = to_key("mTOR – Rapamycin (10 mg/kg) · α-Klotho ✓")
    assert key and all(c.isascii() and (c.islower() or c.isdigit()) for c in key)


# --- find_quote ------------------------------------------------------------------

PAGES = [
    to_key("Introduction. Ageing is a complex process."),
    to_key("We show that Autophagy declines with age in many tissues of mice."),
    to_key("Again: autophagy declines with age in many tissues, as noted."),
]


def test_find_quote_returns_one_based_page():
    assert find_quote(QUOTE, PAGES[:2]) == 2


def test_find_quote_returns_first_page_when_on_several():
    assert find_quote(QUOTE, PAGES) == 2


def test_find_quote_matches_across_messy_pdf_text():
    pages = [to_key("Macroautoph-\nagy is the main route for clearing organelles")]
    assert find_quote("macroautophagy is the main route for clearing", pages) == 1


def test_find_quote_none_when_a_word_is_changed():
    assert find_quote("autophagy increases with age in many tissues", PAGES) is None


def test_find_quote_none_when_a_word_is_added():
    assert find_quote("autophagy strongly declines with age in many", PAGES) is None


def test_find_quote_none_when_a_word_is_removed():
    assert find_quote("autophagy declines age in many tissues", PAGES) is None


def test_find_quote_none_for_empty_key_quote():
    assert find_quote(" -- ... !!! “” ", PAGES) is None
    assert find_quote("", PAGES) is None


def test_find_quote_none_when_quote_spans_page_break():
    pages = [to_key("the first half of the sentence"), to_key("ends on the next page")]
    assert find_quote("half of the sentence ends on the next", pages) is None


def test_find_quote_none_with_no_pages():
    assert find_quote(QUOTE, []) is None


# --- Receipt validation ----------------------------------------------------------


def test_receipt_valid_and_frozen():
    r = Receipt(source="review2023", quote=QUOTE, page=2)
    assert (r.source, r.quote, r.page) == ("review2023", QUOTE, 2)
    with pytest.raises(ValidationError):
        r.page = 3


def test_receipt_accepts_quote_of_exactly_20_characters():
    Receipt(source="s", quote="a" * 20, page=1)


@pytest.mark.parametrize(
    "fields",
    [
        {"source": "s", "quote": "a" * 19, "page": 1},  # short quote
        {"source": "", "quote": QUOTE, "page": 1},  # empty source
        {"source": "s", "quote": QUOTE, "page": 0},  # page < 1
        {"source": "s", "quote": QUOTE, "page": -1},
        {"source": "s", "quote": QUOTE, "page": 1, "note": "x"},  # unknown field
    ],
)
def test_receipt_rejects_bad_fields(fields):
    with pytest.raises(ValidationError):
        Receipt(**fields)


# --- check_receipts --------------------------------------------------------------

BY_SOURCE = {"review2023": PAGES}


def test_check_receipts_all_good_gives_empty_list():
    receipts = [("card-1", Receipt(source="review2023", quote=QUOTE, page=2))]
    assert check_receipts(receipts, BY_SOURCE) == []


def test_check_receipts_empty_input_gives_empty_list():
    assert check_receipts([], BY_SOURCE) == []


def test_check_receipts_wrong_page():
    receipts = [("card-1", Receipt(source="review2023", quote=QUOTE, page=3))]
    assert check_receipts(receipts, BY_SOURCE) == [
        "card-1: quote is on page 2, receipt says 3"
    ]


def test_check_receipts_quote_not_found():
    bad = "autophagy increases with age in many tissues"
    receipts = [("card-2", Receipt(source="review2023", quote=bad, page=2))]
    assert check_receipts(receipts, BY_SOURCE) == [
        "card-2: quote not found in review2023"
    ]


def test_check_receipts_unknown_source_is_a_line_not_a_crash():
    receipts = [("card-3", Receipt(source="nosuch", quote=QUOTE, page=1))]
    assert check_receipts(receipts, BY_SOURCE) == ["card-3: unknown source nosuch"]


def test_check_receipts_keeps_order_given():
    receipts = [
        ("c", Receipt(source="nosuch", quote=QUOTE, page=1)),
        ("a", Receipt(source="review2023", quote=QUOTE, page=2)),  # good
        ("b", Receipt(source="review2023", quote=QUOTE, page=1)),
        ("d", Receipt(source="review2023", quote="x" * 25, page=1)),
    ]
    assert check_receipts(receipts, BY_SOURCE) == [
        "c: unknown source nosuch",
        "b: quote is on page 2, receipt says 1",
        "d: quote not found in review2023",
    ]


# --- Source / load_source --------------------------------------------------------


def test_load_source_reads_fields_and_path(tmp_path):
    src = load_source(write_record(tmp_path, source_record()))
    assert isinstance(src, Source)
    assert src.id == "review2023"
    assert src.url == "https://example.org/review.pdf"
    assert src.size == len(DOC)
    assert src.sha256 == DOC_SHA
    assert src.path(tmp_path) == tmp_path / "sources/review.pdf"


def test_load_source_allows_extra_fields(tmp_path):
    record = source_record(authors=["A. Author"], doi="10.1/x", licence="CC-BY")
    assert load_source(write_record(tmp_path, record)).id == "review2023"


def test_source_is_frozen(tmp_path):
    src = load_source(write_record(tmp_path, source_record()))
    with pytest.raises(ValidationError):
        src.id = "other"


@pytest.mark.parametrize(
    "field", ["id", "title", "url", "size", "sha256", "local_path"]
)
def test_load_source_rejects_missing_field(tmp_path, field):
    record = source_record()
    del record[field]
    with pytest.raises(ValidationError):
        load_source(write_record(tmp_path, record))


@pytest.mark.parametrize(
    "overrides",
    [
        {"url": "http://example.org/review.pdf"},  # not https
        {"url": "ftp://example.org/review.pdf"},
        {"sha256": "abc123"},  # too short
        {"sha256": "z" * 64},  # not hex
        {"sha256": DOC_SHA + "0"},  # 65 characters
        {"size": 0},
        {"size": -5},
    ],
)
def test_load_source_rejects_bad_values(tmp_path, overrides):
    with pytest.raises(ValidationError):
        load_source(write_record(tmp_path, source_record(**overrides)))


def test_load_source_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_source(tmp_path / "nope.json")


# --- ensure_source ---------------------------------------------------------------


@pytest.fixture
def source(tmp_path) -> Source:
    return load_source(write_record(tmp_path, source_record()))


def test_ensure_source_downloads_when_missing(tmp_path, source):
    fetch = FakeFetch()
    path = ensure_source(source, tmp_path, fetch=fetch)
    assert path == source.path(tmp_path)
    assert path.read_bytes() == DOC
    assert fetch.calls == ["https://example.org/review.pdf"]


def test_ensure_source_skips_fetch_when_correct_copy_present(tmp_path, source):
    dest = source.path(tmp_path)
    dest.parent.mkdir(parents=True)
    dest.write_bytes(DOC)
    fetch = FakeFetch()
    assert ensure_source(source, tmp_path, fetch=fetch) == dest
    assert fetch.calls == []


def test_ensure_source_redownloads_wrong_copy(tmp_path, source):
    dest = source.path(tmp_path)
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"X" * len(DOC))  # right size, wrong SHA-256
    fetch = FakeFetch()
    assert ensure_source(source, tmp_path, fetch=fetch) == dest
    assert dest.read_bytes() == DOC
    assert len(fetch.calls) == 1


def test_ensure_source_wrong_size_from_fetch_raises_and_saves_nothing(tmp_path, source):
    with pytest.raises(DownloadError):
        ensure_source(source, tmp_path, fetch=FakeFetch(DOC + b"extra"))
    assert not source.path(tmp_path).exists()


def test_ensure_source_wrong_sha_from_fetch_raises_and_saves_nothing(tmp_path, source):
    wrong = b"Y" * len(DOC)
    with pytest.raises(DownloadError):
        ensure_source(source, tmp_path, fetch=FakeFetch(wrong))
    assert not source.path(tmp_path).exists()


def test_ensure_source_failed_download_raises_download_error(tmp_path, source):
    def broken(url: str) -> bytes:
        raise OSError("connection reset")

    with pytest.raises(DownloadError):
        ensure_source(source, tmp_path, fetch=broken)
    assert not source.path(tmp_path).exists()


# --- page_keys -------------------------------------------------------------------


def make_blank_pdf(path: Path, n_pages: int) -> Path:
    writer = PdfWriter()
    for _ in range(n_pages):
        writer.add_blank_page(width=200, height=200)
    with path.open("wb") as f:
        writer.write(f)
    return path


def test_page_keys_blank_page_gives_empty_string(tmp_path):
    assert page_keys(make_blank_pdf(tmp_path / "one.pdf", 1)) == [""]


def test_page_keys_one_key_per_page(tmp_path):
    keys = page_keys(make_blank_pdf(tmp_path / "three.pdf", 3))
    assert keys == ["", "", ""]


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


def test_page_keys_text_pages_in_order(tmp_path):
    pdf = make_text_pdf(
        tmp_path / "text.pdf", ["Hallmarks of Ageing", "", "Rapamycin inhibits mTOR"]
    )
    # sanity: the helper made a real text PDF (independent of the block)
    assert "Rapamycin" in PdfReader(pdf).pages[2].extract_text()
    assert page_keys(pdf) == ["hallmarksofageing", "", "rapamycininhibitsmtor"]


def test_page_keys_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        page_keys(tmp_path / "nope.pdf")


# --- Added after the SPEC closed the first gap list ---------------------------


@pytest.mark.parametrize("field", ["id", "title", "local_path"])
@pytest.mark.parametrize("value", ["", "   "])
def test_load_source_rejects_empty_or_spaces_only_text(tmp_path, field, value):
    with pytest.raises(ValidationError):
        load_source(write_record(tmp_path, source_record(**{field: value})))


def test_load_source_rejects_upper_case_hex_sha(tmp_path):
    record = source_record(sha256=DOC_SHA.upper())
    assert record["sha256"] != DOC_SHA  # the digest has letters to upper-case
    with pytest.raises(ValidationError):
        load_source(write_record(tmp_path, record))


@pytest.mark.parametrize(
    "local_path",
    [
        "/etc/review.pdf",  # posix absolute
        "C:/x/review.pdf",  # Windows absolute
        "C:\\x\\review.pdf",
        "../review.pdf",
        "data/../../review.pdf",
        "data\\..\\x",  # backslash form
        "C:x/review.pdf",  # drive-relative
        "\\\\server\\share\\review.pdf",  # UNC network path
    ],
)
def test_load_source_rejects_path_that_could_escape_root(tmp_path, local_path):
    with pytest.raises(ValidationError):
        load_source(write_record(tmp_path, source_record(local_path=local_path)))


def test_load_source_accepts_double_dot_inside_a_name(tmp_path):
    """'..' is only rejected as a whole path segment."""
    src = load_source(
        write_record(tmp_path, source_record(local_path="data/raw/file..pdf"))
    )
    assert src.path(tmp_path) == tmp_path / "data/raw/file..pdf"


def test_load_source_invalid_json_raises(tmp_path):
    path = tmp_path / "source.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_source(path)


def test_load_source_extra_fields_are_not_stored(tmp_path):
    record = source_record(authors=["A. Author"], doi="10.1/x")
    src = load_source(write_record(tmp_path, record))
    assert not hasattr(src, "doi")
    assert not hasattr(src, "authors")


@pytest.mark.parametrize("attr", ["source", "quote", "page"])
def test_receipt_assignment_raises(attr):
    r = Receipt(source="review2023", quote=QUOTE, page=2)
    with pytest.raises(ValidationError):
        setattr(r, attr, r.page if attr == "page" else "something else entirely")


@pytest.mark.parametrize("attr", ["url", "size", "local_path"])
def test_source_assignment_raises(tmp_path, attr):
    src = load_source(write_record(tmp_path, source_record()))
    with pytest.raises(ValidationError):
        setattr(src, attr, getattr(src, attr))


@pytest.mark.parametrize("quote", [" " * 5 + "a" * 19 + " " * 5, "\n  " + "b" * 19])
def test_receipt_quote_length_counted_after_stripping(quote):
    assert len(quote) >= 20
    with pytest.raises(ValidationError):
        Receipt(source="s", quote=quote, page=1)


def test_receipt_rejects_spaces_only_source():
    with pytest.raises(ValidationError):
        Receipt(source="   ", quote=QUOTE, page=1)


def test_ensure_source_returns_source_path_after_download(tmp_path, source):
    assert ensure_source(source, tmp_path, fetch=FakeFetch()) == source.path(tmp_path)


def test_ensure_source_returns_source_path_when_copy_present(tmp_path, source):
    dest = source.path(tmp_path)
    dest.parent.mkdir(parents=True)
    dest.write_bytes(DOC)
    assert ensure_source(source, tmp_path, fetch=FakeFetch()) == source.path(tmp_path)


def test_ensure_source_bad_redownload_leaves_older_wrong_copy(tmp_path, source):
    dest = source.path(tmp_path)
    dest.parent.mkdir(parents=True)
    old = b"old wrong copy"
    dest.write_bytes(old)
    with pytest.raises(DownloadError):
        ensure_source(source, tmp_path, fetch=FakeFetch(b"Z" * len(DOC)))
    assert dest.read_bytes() == old


@pytest.mark.parametrize(
    "content",
    [b"this is not a pdf at all", b"%PDF-1.4\n%%garbage, truncated"],
)
def test_page_keys_corrupt_or_non_pdf_raises(tmp_path, content):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(content)
    result = None
    with pytest.raises(Exception) as excinfo:
        result = page_keys(bad)
    assert result is None  # not swallowed into a list
    assert not isinstance(excinfo.value, FileNotFoundError)


# --- Added after the SPEC revision (keys, short keys, path guard, check_all) -----


def test_key_greek_letters_become_names():
    assert to_key("IL-1α") != to_key("IL-1β")
    assert "alpha" in to_key("IL-1α")
    assert to_key("IL-1α") == "il1alpha"


@pytest.mark.parametrize(
    "text, key",
    [
        ("≥ 50%", "ge50pct"),
        ("≤ 50%", "le50pct"),
        ("< 5", "lt5"),
        ("> 5", "gt5"),
        ("± 2", "pm2"),
        ("x = 3", "xeq3"),
    ],
)
def test_key_comparison_signs_become_words(text, key):
    assert to_key(text) == key


def test_key_greater_and_less_or_equal_differ():
    assert to_key("≥ 50%") != to_key("≤ 50%")


def test_key_decimal_point_between_digits_is_kept():
    assert to_key("1.5") == "1dot5"
    assert to_key("1.5") != to_key("15")


def test_key_comma_followed_by_space_is_not_a_decimal():
    assert "dot" not in to_key("1, 2")
    assert to_key("1, 2") == "12"


def test_key_known_limit_resplit_word_still_matches():
    """Documented limit: spaces are dropped, so 'a part' == 'apart'."""
    assert to_key("a part") == to_key("apart")


def test_receipt_rejects_quote_whose_key_is_short_even_if_raw_is_long():
    quote = "a . . . . . . . . . b"
    assert len(quote) >= 20 and len(to_key(quote)) < 20
    with pytest.raises(ValidationError):
        Receipt(source="s", quote=quote, page=1)


def test_source_path_raises_when_it_resolves_outside_root(tmp_path):
    """Through the public API only a symlink inside root can point outside it."""
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (root / "sources").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("cannot create symlinks here")
    src = load_source(write_record(tmp_path, source_record()))
    with pytest.raises(ValueError):
        src.path(root)


# --- check_all -------------------------------------------------------------------

PAGE_TEXTS = [
    "Introduction to ageing research",
    "Autophagy declines with age in many tissues of mice",
]


@pytest.fixture
def pdf_bytes(tmp_path) -> bytes:
    return make_text_pdf(tmp_path / "made.pdf", PAGE_TEXTS).read_bytes()


class UrlFetch:
    """Fake fetch: url -> bytes (or an exception to raise); records calls."""

    def __init__(self, by_url: dict):
        self.by_url = by_url
        self.calls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        value = self.by_url[url]
        if isinstance(value, Exception):
            raise value
        return value


def add_source(sources_dir: Path, sid: str, data: bytes, file_id: str | None = None):
    """Write <file_id or sid>.json pinning `data`; return its URL."""
    sources_dir.mkdir(exist_ok=True)
    url = f"https://example.org/{sid}.pdf"
    record = {
        "id": sid,
        "title": f"Title {sid}",
        "url": url,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "local_path": f"docs/{sid}.pdf",
    }
    path = sources_dir / f"{file_id or sid}.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return url


GOOD_QUOTE = "autophagy declines with age in many tissues"


def r(source: str, page: int = 2, quote: str = GOOD_QUOTE) -> Receipt:
    return Receipt(source=source, quote=quote, page=page)


def test_check_all_all_good_gives_empty_list(tmp_path, pdf_bytes):
    sdir = tmp_path / "sources"
    url = add_source(sdir, "rev", pdf_bytes)
    fetch = UrlFetch({url: pdf_bytes})
    assert check_all([("c1", r("rev"))], sdir, tmp_path, fetch=fetch) == []


def test_check_all_not_found_and_wrong_page_lines(tmp_path, pdf_bytes):
    sdir = tmp_path / "sources"
    url = add_source(sdir, "rev", pdf_bytes)
    receipts = [
        ("c1", r("rev", quote="autophagy increases with age in many tissues")),
        ("c2", r("rev", page=1)),
    ]
    assert check_all(receipts, sdir, tmp_path, fetch=UrlFetch({url: pdf_bytes})) == [
        "c1: quote not found in rev",
        "c2: quote is on page 2, receipt says 1",
    ]


def test_check_all_missing_record_one_line_per_citing_receipt(tmp_path, pdf_bytes):
    sdir = tmp_path / "sources"
    url = add_source(sdir, "rev", pdf_bytes)
    receipts = [("c1", r("ghost")), ("c2", r("rev")), ("c3", r("ghost"))]
    assert check_all(receipts, sdir, tmp_path, fetch=UrlFetch({url: pdf_bytes})) == [
        "c1: no source record ghost.json",
        "c3: no source record ghost.json",
    ]


def _assert_unusable_lines(lines: list[str], labels: list[str]):
    assert len(lines) == len(labels)
    for line, label in zip(lines, labels):
        assert line.startswith(f"{label}: ")
        assert "unusable" in line or "unreadable" in line


def test_check_all_record_id_differs_from_file_name(tmp_path, pdf_bytes):
    sdir = tmp_path / "sources"
    url = add_source(sdir, "other", pdf_bytes, file_id="rev")
    receipts = [("c1", r("rev")), ("c2", r("rev"))]
    lines = check_all(receipts, sdir, tmp_path, fetch=UrlFetch({url: pdf_bytes}))
    _assert_unusable_lines(lines, ["c1", "c2"])


def test_check_all_fetch_raising_gives_a_line(tmp_path, pdf_bytes):
    sdir = tmp_path / "sources"
    url = add_source(sdir, "rev", pdf_bytes)
    fetch = UrlFetch({url: OSError("connection reset")})
    lines = check_all([("c1", r("rev"))], sdir, tmp_path, fetch=fetch)
    _assert_unusable_lines(lines, ["c1"])


def test_check_all_corrupt_pdf_gives_a_line(tmp_path):
    """Pinned bytes match (size + SHA) but are not a PDF."""
    junk = b"this is definitely not a pdf document"
    sdir = tmp_path / "sources"
    url = add_source(sdir, "rev", junk)
    lines = check_all([("c1", r("rev"))], sdir, tmp_path, fetch=UrlFetch({url: junk}))
    _assert_unusable_lines(lines, ["c1"])


def test_check_all_fetches_each_source_once(tmp_path, pdf_bytes):
    sdir = tmp_path / "sources"
    url = add_source(sdir, "rev", pdf_bytes)
    fetch = UrlFetch({url: pdf_bytes})
    receipts = [("c1", r("rev")), ("c2", r("rev", page=1)), ("c3", r("rev"))]
    lines = check_all(receipts, sdir, tmp_path, fetch=fetch)
    assert lines == ["c2: quote is on page 2, receipt says 1"]
    assert fetch.calls == [url]


# --- Accented Greek letters, key-length rule, invalid-JSON record in check_all ---


def test_key_accented_greek_maps_to_base_letter():
    assert to_key("ά") == to_key("α") == "alpha"
    assert to_key("έ") == "epsilon"
    assert to_key("ά") != to_key("έ")


def test_receipt_accepts_short_raw_quote_whose_key_is_long():
    """The 20-character rule is on the key, not the raw text."""
    quote = "IL-1β ≥ 2.5% α"
    assert len(quote) < 20 and len(to_key(quote)) >= 20
    assert Receipt(source="s", quote=quote, page=1).quote


@pytest.mark.parametrize("content", ["{not json", '{"id": "rev"}'])
def test_check_all_bad_record_file_gives_unusable_line(tmp_path, content):
    """A record that exists but is invalid JSON or fails validation: 'unusable'."""
    sdir = tmp_path / "sources"
    sdir.mkdir()
    (sdir / "rev.json").write_text(content, encoding="utf-8")
    lines = check_all([("c1", r("rev"))], sdir, tmp_path, fetch=UrlFetch({}))
    assert len(lines) == 1
    assert lines[0].startswith("c1: ")
    assert "unusable" in lines[0]
    assert "no source record" not in lines[0]
