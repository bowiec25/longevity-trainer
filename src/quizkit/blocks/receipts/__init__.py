"""receipts: Check that a quote really appears, word for word, in a pinned source document, and on which page.

See SPEC.md in this folder (ADR 0003). Generic: any quiz with sourced cards can use it.
Both sides are reduced to a "key" (lower-case ASCII letters and digits), so PDF mess
(ligatures, line-end hyphens, curly quotes, split accents) doesn't matter, but a
changed word still does.
"""

import json
import re
import unicodedata
from collections.abc import Callable
from pathlib import Path, PurePosixPath, PureWindowsPath

from pydantic import BaseModel, ConfigDict, Field, field_validator

from quizkit.blocks.base import BlockSpec
from quizkit.blocks.source_text import FORMATS, text_pages
from quizkit.download import DownloadError, download_verified, http_get

BLOCK_SPEC = BlockSpec(
    name="receipts",
    kind="script",
    goal="Check that a quote really appears, word for word, in a pinned source document, and on which page.",
    inputs=[
        "source_file",
        "root",
        "fetch",
        "pdf_path",
        "format",
        "quote",
        "pages",
        "receipts",
        "pages_by_source",
        "sources_dir",
    ],
    outputs=[
        "to_key",
        "Receipt",
        "Source",
        "ensure_source",
        "page_keys",
        "find_quote",
        "check_receipts",
        "check_all",
    ],
)


# Symbols a science quote turns on, kept as words so "≥ 50%" ≠ "≤ 50%".
SYMBOLS = {"≥": "ge", "≤": "le", "<": "lt", ">": "gt", "%": "pct", "±": "pm", "=": "eq"}
DECIMAL = re.compile(r"(?<=\d)[.,·](?=\d)")  # 1.5 ≠ 15 (but "1, 2" stays a list)


def _symbol(ch: str) -> str:
    if ch in SYMBOLS:
        return SYMBOLS[ch]
    base = unicodedata.normalize("NFD", ch)[0]  # ά -> α + accent: keep α
    words = unicodedata.name(base, "").split()
    if words[:1] == ["GREEK"] and "LETTER" in words:  # α -> alpha (IL-1α ≠ IL-1β)
        return words[words.index("LETTER") + 1].lower()
    return ""


def to_key(text: str) -> str:
    """The text as a comparison key: lower-case ASCII letters, digits and symbol
    words. Ligatures become letters, accents are dropped, Greek letters and the
    symbols above become words, a decimal point between digits becomes "dot";
    spaces, hyphens, quotes and other punctuation disappear."""
    text = DECIMAL.sub("dot", unicodedata.normalize("NFKC", text))
    out = []
    for ch in text:
        word = _symbol(ch)
        if word:
            out.append(word)
            continue
        for part in unicodedata.normalize("NFKD", ch).lower():
            if part.isascii() and part.isalnum():
                out.append(part)
    return "".join(out)


class Receipt(BaseModel):
    """Proof for a card: which source, the word-for-word quote, and its page."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    source: str = Field(min_length=1)
    quote: str
    page: int = Field(
        ge=1,
        description="PDF page (1 = the file's first page); always 1 for html or jats-xml",
    )

    @field_validator("quote")
    @classmethod
    def key_long_enough(cls, quote: str) -> str:
        if len(to_key(quote)) < 20:  # "a . . . . b" would match almost anything
            raise ValueError("the quote's key must have at least 20 characters")
        return quote


class Source(BaseModel):
    """A pinned source record: exactly which document, and where it's kept."""

    model_config = ConfigDict(frozen=True, extra="ignore", str_strip_whitespace=True)

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: str = Field(pattern=r"^https://")
    size: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    local_path: str = Field(min_length=1)
    format: str = "pdf"  # one of source_text.FORMATS

    @field_validator("local_path")
    @classmethod
    def stays_inside_root(cls, local_path: str) -> str:
        win = PureWindowsPath(local_path)  # catches C:/x, C:x and \\server\share too
        parts = PurePosixPath(local_path.replace("\\", "/")).parts
        if win.drive or win.root or local_path.startswith("/") or ".." in parts:
            raise ValueError("local_path must be relative and must not contain '..'")
        return local_path

    @field_validator("format")
    @classmethod
    def known_format(cls, format: str) -> str:
        if format not in FORMATS:
            raise ValueError(f"format must be one of {FORMATS}")
        return format

    def path(self, root: Path) -> Path:
        root = Path(root)
        full = root / self.local_path
        if not full.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"{self.local_path!r} resolves outside {root}")
        return full


def load_source(source_file: Path) -> Source:
    return Source.model_validate(json.loads(Path(source_file).read_text("utf-8")))


def ensure_source(
    source: Source, root: Path, fetch: Callable[[str], bytes] = http_get
) -> Path:
    """Download the document if missing or wrong; always verify size + SHA-256."""
    dest = source.path(root)
    download_verified(
        source.url, dest, size=source.size, sha256=source.sha256, fetch=fetch
    )
    return dest


def page_keys(pdf_path: Path, format: str = "pdf") -> list[str]:
    """The key of each page's text, in order (index 0 = page 1)."""
    return [to_key(text) for text in text_pages(pdf_path, format)]


def find_quote(quote: str, pages: list[str]) -> int | None:
    """The first 1-based page whose key contains the quote's key, or None."""
    key = to_key(quote)
    if not key:  # an empty key would match every page
        return None
    for number, page in enumerate(pages, start=1):
        if key in page:
            return number
    return None


def check_receipts(
    receipts: list[tuple[str, Receipt]], pages_by_source: dict[str, list[str]]
) -> list[str]:
    """One problem line per bad receipt, in order; [] = every quote on its page."""
    problems = []
    for label, receipt in receipts:
        pages = pages_by_source.get(receipt.source)
        if pages is None:
            problems.append(f"{label}: unknown source {receipt.source}")
            continue
        found = find_quote(receipt.quote, pages)
        if found is None:
            problems.append(f"{label}: quote not found in {receipt.source}")
        elif found != receipt.page:
            problems.append(
                f"{label}: quote is on page {found}, receipt says {receipt.page}"
            )
    return problems


def _one_line(text: str) -> str:
    return text.splitlines()[0]


def check_all(
    receipts: list[tuple[str, Receipt]],
    sources_dir: Path,
    root: Path,
    fetch: Callable[[str], bytes] = http_get,
) -> list[str]:
    """Load, fetch and read each source once, then check every receipt.

    A source that can't be used (no record, a record for another id, a bad record,
    a failed download, an unreadable document) gives ONE problem line per receipt that
    cites it, never a traceback. [] = every quote found on its page.
    """
    pages: dict[str, list[str]] = {}
    broken: dict[str, str] = {}
    for source_id in sorted({r.source for _, r in receipts}):
        record = Path(sources_dir) / f"{source_id}.json"
        try:
            source = load_source(record)
        except FileNotFoundError:
            broken[source_id] = f"no source record {record.name}"
            continue
        except ValueError as err:  # invalid JSON or a bad record
            broken[source_id] = _one_line(f"source {source_id} unusable ({err})")
            continue
        try:
            if source.id != source_id:
                raise ValueError(f"{record.name} is for {source.id!r}")
            document = ensure_source(source, root, fetch)
            pages[source_id] = page_keys(document, source.format)
        except (ValueError, DownloadError, OSError) as err:
            broken[source_id] = _one_line(f"source {source_id} unusable ({err})")
        except Exception as err:  # noqa: BLE001 (a corrupt PDF: pypdf raises its own errors)
            broken[source_id] = f"source {source_id} unreadable ({type(err).__name__})"
    problems = []
    for label, receipt in receipts:
        if receipt.source in broken:
            problems.append(f"{label}: {broken[receipt.source]}")
        else:
            problems.extend(check_receipts([(label, receipt)], pages))
    return problems
