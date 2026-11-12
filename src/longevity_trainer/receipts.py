"""Receipts: check that every card's quote really is in its pinned source.

A receipt = a source id + a word-for-word quote + the PDF page it is on.
PDF text is messy (ligatures, hyphenated line breaks, curly quotes, split accents),
so both sides are reduced to a "key": lower-case letters and digits only.
Changing, adding or removing one word still breaks the match.

Run all checks:  uv run python -m longevity_trainer.receipts
"""

import json
import logging
import unicodedata
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from quizkit.download import download_verified

ROOT = Path(__file__).resolve().parents[2]
SOURCES_DIR = ROOT / "data" / "sources"


def to_key(text: str) -> str:
    """Reduce text to lower-case letters and digits, so PDF quirks don't matter."""
    # NFKD: ligatures become letters, accents split off (then dropped as non-ASCII)
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text.lower() if ch.isascii() and ch.isalnum())


@dataclass(frozen=True)
class Source:
    id: str
    title: str
    url: str
    size: int
    sha256: str
    local_path: str

    @property
    def path(self) -> Path:
        return ROOT / self.local_path


def load_source(source_id: str, sources_dir: Path = SOURCES_DIR) -> Source:
    data = json.loads((sources_dir / f"{source_id}.json").read_text(encoding="utf-8"))
    return Source(
        id=data["id"],
        title=data["title"],
        url=data["url"],
        size=data["size"],
        sha256=data["sha256"],
        local_path=data["local_path"],
    )


def _fetch(url: str) -> bytes:
    # Some repositories refuse Python's default user agent; use a generic one.
    request = urllib.request.Request(url, headers={"User-Agent": "longevity-trainer"})
    with urllib.request.urlopen(request, timeout=60) as response:  # pinned https URL
        return response.read()


def ensure_source(source: Source) -> Path:
    """Download the source if it's missing; always check size + SHA-256."""
    download_verified(
        source.url, source.path, size=source.size, sha256=source.sha256, fetch=_fetch
    )
    return source.path


def page_keys(pdf_path: Path) -> list[str]:
    """The key of each PDF page's text (index 0 = page 1)."""
    from pypdf import PdfReader  # only needed when checking against a real PDF

    logging.getLogger("pypdf").setLevel(logging.ERROR)  # font warnings are noise here
    return [to_key(page.extract_text() or "") for page in PdfReader(pdf_path).pages]


def find_quote(quote: str, pages: list[str]) -> int | None:
    """The 1-based page the quote is on, or None if it isn't in the source."""
    key = to_key(quote)
    if not key:
        return None
    for number, page in enumerate(pages, start=1):
        if key in page:
            return number
    return None


def check_receipts(cards, pages_by_source: dict[str, list[str]]) -> list[str]:
    """Return one problem line per bad receipt (empty list = all good)."""
    problems = []
    for card in cards:
        r = card.receipt
        page = find_quote(r.quote, pages_by_source[r.source])
        if page is None:
            problems.append(f"{card.id}: quote not found in {r.source}")
        elif page != r.page:
            problems.append(f"{card.id}: quote is on page {page}, card says {r.page}")
    return problems


def main() -> int:
    from longevity_trainer.cards import load_cards

    cards = load_cards()
    pages = {}
    for source_id in sorted({c.receipt.source for c in cards}):
        pages[source_id] = page_keys(ensure_source(load_source(source_id)))
    problems = check_receipts(cards, pages)
    for line in problems:
        print(line)
    print(f"receipts: {len(cards) - len(problems)}/{len(cards)} quotes found")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
