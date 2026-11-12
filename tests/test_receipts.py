"""Receipts: every card's quote must be found, word for word, in its pinned source."""

import pytest

from longevity_trainer.cards import load_cards
from longevity_trainer.receipts import (
    check_receipts,
    find_quote,
    load_source,
    page_keys,
    to_key,
)


def test_key_ignores_pdf_quirks():
    pdf = "macroautoph-\nagy is a ﬁrst  line of ‘‘defense’’ in all-\ncause"
    assert to_key(pdf) == to_key(
        'macroautophagy is a first line of "defense" in allcause'
    )


def test_key_strips_split_accents():
    assert to_key("López-Otín") == to_key("López-Otín") == "lopezotin"


PAGES = [
    to_key("Cover page."),
    to_key("Most mammalian somatic cells do not express telomerase."),
]


def test_find_quote_returns_its_page():
    assert (
        find_quote("most mammalian somatic cells do not express telomerase", PAGES) == 2
    )


def test_changing_one_word_breaks_the_match():
    assert (
        find_quote("most mammalian somatic cells do express telomerase", PAGES) is None
    )


def test_empty_quote_never_matches():
    assert find_quote("…", PAGES) is None


def test_cards_load_and_have_unique_ids():
    cards = load_cards()
    assert len(cards) == 15
    assert all(c.to_quizkit().answers for c in cards)


def test_every_card_source_is_pinned():
    for source_id in {c.receipt.source for c in load_cards()}:
        source = load_source(source_id)
        assert source.url.startswith("https://")
        assert len(source.sha256) == 64


def test_real_quotes_are_in_the_real_source():
    """Skips when the PDF isn't downloaded (CI): run `python -m longevity_trainer.receipts`."""
    cards = load_cards()
    pages = {}
    for source_id in {c.receipt.source for c in cards}:
        source = load_source(source_id)
        if not source.path.is_file():
            pytest.skip(f"{source.path.name} not downloaded")
        pages[source_id] = page_keys(source.path)
    assert check_receipts(cards, pages) == []
