"""The card eval set (tests/data/card_eval.md) stays a fair exam.

Every card is a valid LongevityCard, ids are unique, verdicts and rules agree,
each rule the checker owns has at least two bad cards, and every quote is really
in its pinned source (skipped when the documents aren't downloaded, as in CI).
"""

import json
from collections import Counter
from pathlib import Path

import pytest

from longevity_trainer.blocks.card_bank import ROOT, LongevityCard
from quizkit.blocks.receipts import find_quote, load_source, page_keys

EVAL = ROOT / "tests" / "data" / "card_eval.jsonl"
CHECKER_RULES = (2, 3, 4, 5, 6)  # rule 1 is per topic, rule 7 waits for M5


def cases() -> list[dict]:
    return [json.loads(line) for line in EVAL.read_text("utf-8").splitlines() if line]


def test_every_line_has_the_fields_and_a_valid_card():
    for case in cases():
        assert set(case) == {"id", "expected", "rules", "why", "origin", "card"}, case
        assert case["why"].strip() and case["origin"].strip(), case["id"]
        assert LongevityCard.model_validate(case["card"]).id == case["id"]


def test_ids_are_unique():
    ids = Counter(case["id"] for case in cases())
    assert [i for i, n in ids.items() if n > 1] == []


def test_verdict_and_rule_agree():
    for case in cases():
        rules = case["rules"]
        if case["expected"] == "pass":
            assert rules == [], case["id"]
        else:
            assert case["expected"] == "fail", case["id"]
            assert rules and set(rules) <= set(CHECKER_RULES), case["id"]
            assert len(rules) == len(set(rules)), case["id"]


def test_enough_cards_on_each_side():
    verdicts = Counter(case["expected"] for case in cases())
    assert verdicts["pass"] >= 10 and verdicts["fail"] >= 10
    # a card counts toward each rule it may be caught under
    rules = Counter(
        r for case in cases() if case["expected"] == "fail" for r in case["rules"]
    )
    assert {rule: rules[rule] for rule in CHECKER_RULES if rules[rule] < 2} == {}


def test_every_quote_is_on_its_page_of_the_pinned_source():
    keys: dict[str, list[str]] = {}
    for case in cases():
        receipt = LongevityCard.model_validate(case["card"]).receipt
        if receipt.source not in keys:
            source = load_source(ROOT / "data" / "sources" / f"{receipt.source}.json")
            document: Path = source.path(ROOT)
            if not document.is_file():
                pytest.skip(f"{document.name} not downloaded (CI)")
            keys[receipt.source] = page_keys(document, source.format)
        assert find_quote(receipt.quote, keys[receipt.source]) == receipt.page, case[
            "id"
        ]
