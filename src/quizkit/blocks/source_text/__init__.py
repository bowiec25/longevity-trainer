"""source_text: Turn a pinned source (PDF, HTML page or JATS XML) into plain-text pages, so a quote can be checked in any format.

See SPEC.md in this folder (ADR 0003).
"""

import logging
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

from quizkit.blocks.base import BlockSpec

BLOCK_SPEC = BlockSpec(
    name="source_text",
    kind="script",
    goal="Turn a pinned source (PDF, HTML page or JATS XML) into plain-text pages, so a quote can be checked in any format.",
    inputs=["path", "format"],
    outputs=["text_pages", "FORMATS"],
)

FORMATS = ("pdf", "html", "jats-xml")

_SPACES = re.compile(r"\s+")


def _tidy(parts: list[str]) -> str:
    return _SPACES.sub(" ", "".join(parts)).strip()


def text_pages(path: Path, format: str) -> list[str]:
    """Plain text of the document, one string per page (index 0 = page 1)."""
    if format not in FORMATS:
        raise ValueError(f"unknown format {format!r}: expected one of {FORMATS}")
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    if format == "pdf":
        return _pdf_pages(path)
    if format == "html":
        return [_html_text(_decode_html(path.read_bytes()))]
    return [_jats_text(path.read_bytes())]


def _pdf_pages(path: Path) -> list[str]:
    from pypdf import PdfReader  # only needed for real documents

    logging.getLogger("pypdf").setLevel(logging.ERROR)  # font warnings are noise
    return [page.extract_text() or "" for page in PdfReader(path).pages]


# Elements whose content is never shown on the page (<head> holds only metadata).
_HIDDEN = {"head", "script", "style", "noscript", "template", "svg"}
# Elements that never have an end tag, so they never stay open.
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
         "param", "source", "track", "wbr"}  # fmt: skip
_DISPLAY_NONE = re.compile(r"display\s*:\s*none", re.IGNORECASE)


def _hides(tag: str, attrs: list[tuple[str, str | None]]) -> bool:
    if tag in _HIDDEN:
        return True
    names = dict(attrs)
    return "hidden" in names or bool(_DISPLAY_NONE.search(names.get("style") or ""))


class _Visible(HTMLParser):
    """Collects visible text; each tag boundary separates words.

    Keeps a stack of open elements. A hidden element stops hiding when it, or any
    element it was opened inside, is closed, so a stray unclosed <noscript> can't
    hide the rest of the page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)  # &amp; and &alpha; decoded
        self.parts: list[str] = []
        self.open: list[str] = []
        self.hidden_at: list[int] = []  # stack depths of open hidden elements

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.parts.append(" ")
        if tag in _VOID:
            return
        self.open.append(tag)
        if _hides(tag, attrs):
            self.hidden_at.append(len(self.open))

    def handle_startendtag(self, tag: str, attrs: object) -> None:
        self.parts.append(" ")  # <br/>, <svg/>: nothing inside to hide

    def handle_endtag(self, tag: str) -> None:
        self.parts.append(" ")
        if tag not in self.open:
            return  # a stray end tag
        depth = len(self.open) - 1 - self.open[::-1].index(tag)
        del self.open[depth:]
        self.hidden_at = [d for d in self.hidden_at if d <= depth]

    def handle_data(self, data: str) -> None:
        if not self.hidden_at:
            self.parts.append(data)


_CHARSET = re.compile(
    rb"""<meta[^>]+charset\s*=\s*["']?([A-Za-z0-9_.:-]+)""", re.IGNORECASE
)


def _decode_html(data: bytes) -> str:
    """Decode with the page's declared charset (a <meta> near the top), else UTF-8."""
    found = _CHARSET.search(data[:4096])
    encoding = found.group(1).decode("ascii") if found else "utf-8"
    try:
        return data.decode(encoding, errors="replace")
    except LookupError:  # a charset name Python doesn't know
        return data.decode("utf-8", errors="replace")


def _html_text(html: str) -> str:
    parser = _Visible()
    parser.feed(html)
    parser.close()
    return _tidy(parser.parts)


# Inline JATS markup: kept inside a word ("rapa<italic>my</italic>cin").
_INLINE = {"italic", "bold", "sup", "sub", "sc", "underline", "monospace", "xref",
           "ext-link", "named-content", "styled-content", "inline-formula", "uri"}  # fmt: skip
# Never article text: someone else's titles (a reference list, wherever the
# publisher put it), author/funding notes, supplementary-file labels, copyright
# lines, and the machine form of formulas.
_SKIP = {"ref-list", "fn-group", "supplementary-material", "permissions", "tex-math",
         "annotation", "annotation-xml"}  # fmt: skip


def _local(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _element_text(el: ET.Element, out: list[str]) -> None:
    """Text of `el` in reading order; block elements are separated by a space."""
    if _local(el.tag) in _SKIP:
        return
    inline = _local(el.tag) in _INLINE
    if not inline:
        out.append(" ")
    if el.text:
        out.append(el.text)
    for child in el:
        _element_text(child, out)
        if child.tail:
            out.append(child.tail)
    if not inline:
        out.append(" ")


def _children(el: ET.Element | None, name: str) -> list[ET.Element]:
    return [] if el is None else [c for c in el if _local(c.tag) == name]


def _jats_text(data: bytes) -> str:
    try:
        root = ET.fromstring(data)  # never fetches the DTD or external entities
    except ET.ParseError as err:
        raise ValueError(f"not valid XML: {err}") from err
    # The article may be wrapped (<pmc-articleset>, OAI-PMH): use the first one.
    article = next((e for e in root.iter() if _local(e.tag) == "article"), None)
    if article is None:
        raise ValueError("no article text (no <article>)")
    fronts = _children(article, "front")
    metas = _children(fronts[0] if fronts else None, "article-meta")
    inside = list(metas[0].iter()) if metas else []
    titles = [e for e in inside if _local(e.tag) == "article-title"]
    abstracts = [e for e in inside if _local(e.tag) == "abstract"]
    bodies = _children(article, "body")
    if not abstracts and not bodies:
        raise ValueError("no article text (no <abstract> or <body>)")
    out: list[str] = []
    for el in titles[:1] + abstracts + bodies + _children(article, "floats-group"):
        _element_text(el, out)
    return _tidy(out)
