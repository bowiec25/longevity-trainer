"""Tests for the study block: its contract (ID card + SPEC.md) and its behaviour.

The behaviour tests were written from SPEC.md "How to test", before the code.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import longevity_trainer.blocks.study as block
from longevity_trainer.blocks.card_bank import load_cards
from longevity_trainer.blocks.study import (
    SKILL,
    Saver,
    deal,
    group_of,
    schedule,
    stats_lines,
)
from quizkit.blocks.base import missing_spec_sections, spec_section
from quizkit.blocks.engine import QuizSession
from quizkit.blocks.progress_store import (
    AnswerRecord,
    BoxState,
    ProgressFileError,
    ProgressStore,
)
from quizkit.modes import Mode, build_question

SPEC_MD = Path(block.__file__).parent / "SPEC.md"
NOW = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)
RIGHT_ID, WRONG_ID = "hm-telomeres-name", "hm-dysbiosis-name"


# --- contract --------------------------------------------------------------------


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "study"
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


@pytest.mark.parametrize("name", ["practise", "next_due", "groups"])
def test_block_spec_lists_the_new_spec_items(name):
    """BLOCK_SPEC was updated with the SPEC's new input and outputs."""
    listed = [*block.BLOCK_SPEC.inputs, *block.BLOCK_SPEC.outputs]
    assert any(name in item for item in listed), f"{name!r} not in BLOCK_SPEC"


# --- helpers ---------------------------------------------------------------------


def card(card_id):
    return next(c for c in load_cards() if c.id == card_id)


def attempt(c, typed):
    """A real, finally-marked Attempt for one card (no judge)."""
    question = build_question(c.to_quizkit(), Mode(name=c.kind, show=["question"]))
    return QuizSession([question]).answer(typed)


@pytest.fixture
def store(tmp_path):
    return ProgressStore(tmp_path / "progress.db", busy_seconds=0.1)


def answer_right_and_wrong(store):
    """Save one right answer (new card) and one wrong one, both at NOW."""
    saver = Saver(store, now=lambda: NOW, warn=lambda _m: None)
    saver(attempt(card(RIGHT_ID), "telomere attrition"))
    saver(attempt(card(WRONG_ID), "no idea"))
    return saver


# --- SKILL and group_of ----------------------------------------------------------


def test_skill_is_recall():
    assert SKILL == "recall"


@pytest.mark.parametrize(
    ("topic", "group"),
    [
        ("hallmarks: dysbiosis", "hallmarks"),
        ("rapamycin", "rapamycin"),
        ("  sleep :  naps", "sleep"),
    ],
)
def test_group_of_is_the_text_before_the_first_colon(topic, group):
    assert group_of(topic) == group


# --- deal ------------------------------------------------------------------------


def five_cards_and_schedule():
    """a, e not due (e sooner); b due; c more overdue; d new."""
    a, b, c, d = (
        card("hm-telomeres-name"),
        card("hm-dysbiosis-name"),
        card("hm-il6-marker"),
        card("hm-telomeres-why"),
    )
    e = b.model_copy(update={"id": "extra-not-due"})
    sched = {
        a.id: NOW + timedelta(days=3),  # not due, later
        e.id: NOW + timedelta(days=1),  # not due, sooner
        b.id: NOW - timedelta(days=1),  # due, overdue by a day
        c.id: NOW - timedelta(days=5),  # due, more overdue
    }  # d is new
    return [a, b, c, d, e], sched


def test_deal_puts_due_first_most_overdue_then_new_and_leaves_out_not_due():
    cards, sched = five_cards_and_schedule()
    _, b, c, d, _ = cards
    dealt = deal(cards, 5, schedule=sched, now=NOW, seed=1)
    assert [x.id for x in dealt] == [c.id, b.id, d.id]  # fewer than n: no fill-up


def test_deal_practise_adds_not_due_cards_after_soonest_first():
    cards, sched = five_cards_and_schedule()
    a, b, c, d, e = cards
    dealt = deal(cards, 5, schedule=sched, now=NOW, seed=1, practise=True)
    assert [x.id for x in dealt] == [c.id, b.id, d.id, e.id, a.id]


def test_deal_practise_still_respects_n():
    cards, sched = five_cards_and_schedule()
    _, b, c, d, e = cards
    dealt = deal(cards, 4, schedule=sched, now=NOW, seed=1, practise=True)
    assert [x.id for x in dealt] == [c.id, b.id, d.id, e.id]


def test_deal_everything_not_due_and_nothing_new_returns_empty_list():
    a, b = card("hm-telomeres-name"), card("hm-dysbiosis-name")
    sched = {a.id: NOW + timedelta(days=3), b.id: NOW + timedelta(days=1)}
    assert deal([a, b], 5, schedule=sched, now=NOW, seed=1) == []


def test_deal_practise_deals_not_due_cards_when_nothing_else_is_left():
    a, b = card("hm-telomeres-name"), card("hm-dysbiosis-name")
    sched = {a.id: NOW + timedelta(days=3), b.id: NOW + timedelta(days=1)}
    dealt = deal([a, b], 5, schedule=sched, now=NOW, seed=1, practise=True)
    assert [x.id for x in dealt] == [b.id, a.id]


def test_deal_n_limits_and_never_repeats():
    dealt = deal(load_cards(), 5, seed=3)
    assert len(dealt) == 5
    assert len({x.id for x in dealt}) == 5


def test_deal_gives_every_card_once_when_n_is_bigger_than_the_bank():
    cards = load_cards()
    dealt = deal(cards, len(cards) + 50, seed=3)
    assert sorted(x.id for x in dealt) == sorted(c.id for c in cards)


def test_deal_topic_is_case_insensitive_and_matches_part_of_a_topic():
    cards = load_cards()
    dealt = deal(cards, 1000, topic="HALLMARKS", seed=1)
    expected = {c.id for c in cards if "hallmarks" in c.topic.lower()}
    assert {x.id for x in dealt} == expected
    assert len({x.topic for x in dealt}) > 1  # every "hallmarks: ..." section


def test_deal_topic_matches_a_fragment():
    dealt = deal(load_cards(), 1000, topic="rapa", seed=1)
    assert dealt
    assert all("rapamycin" in x.topic.lower() for x in dealt)


def test_deal_no_matching_topic_returns_empty_list():
    assert deal(load_cards(), 10, topic="zzz-nothing", seed=1) == []


@pytest.mark.parametrize("n", [0, -1])
def test_deal_n_below_1_raises_value_error(n):
    with pytest.raises(ValueError):
        deal(load_cards(), n, seed=1)


def test_deal_returns_the_longevity_cards_with_receipts_intact():
    cards = {c.id: c for c in load_cards()}
    dealt = deal(list(cards.values()), 3, seed=1)
    assert dealt
    for x in dealt:
        assert x == cards[x.id]
        assert x.receipt.quote


def test_deal_same_seed_gives_same_order():
    cards = load_cards()
    first = [x.id for x in deal(cards, 10, seed=5)]
    assert first == [x.id for x in deal(cards, 10, seed=5)]


def test_deal_ignores_schedule_entries_for_cards_not_in_the_bank():
    a, b = card("hm-telomeres-name"), card("hm-dysbiosis-name")
    sched = {"no-such-card": NOW - timedelta(days=9), b.id: NOW - timedelta(days=1)}
    dealt = deal([a, b], 5, schedule=sched, now=NOW, seed=1)
    assert [x.id for x in dealt] == [b.id, a.id]


def test_deal_now_without_timezone_raises_value_error():
    a = card("hm-telomeres-name")
    with pytest.raises(ValueError):
        deal([a], 1, schedule={a.id: NOW}, now=datetime(2026, 11, 12, 9, 0), seed=1)


# --- next_due ---------------------------------------------------------------------


def test_next_due_is_the_soonest_due_among_matching_cards():
    cards, sched = five_cards_and_schedule()
    _, _, c, _, _ = cards
    assert block.next_due(cards, sched) == sched[c.id]


def test_next_due_topic_narrows_it():
    a = card("hm-telomeres-name")  # "hallmarks: telomere attrition"
    b = card("hm-dysbiosis-name")  # "hallmarks: dysbiosis"
    sched = {a.id: NOW + timedelta(days=3), b.id: NOW + timedelta(days=1)}
    assert block.next_due([a, b], sched) == sched[b.id]
    assert block.next_due([a, b], sched, topic="TELOMERE") == sched[a.id]


def test_next_due_ignores_schedule_entries_for_cards_not_given():
    a = card("hm-telomeres-name")
    sched = {"no-such-card": NOW - timedelta(days=9), a.id: NOW + timedelta(days=2)}
    assert block.next_due([a], sched) == sched[a.id]


def test_next_due_with_no_matching_card_in_the_schedule_is_none():
    a, b = card("hm-telomeres-name"), card("hm-dysbiosis-name")
    assert block.next_due([a, b], {}) is None
    assert block.next_due([a, b], {a.id: NOW}, topic="dysbiosis") is None
    assert block.next_due([a, b], {a.id: NOW}, topic="zzz-nothing") is None


# --- groups -----------------------------------------------------------------------


def test_groups_are_distinct_sorted_and_hallmarks_is_one_group():
    cards = load_cards()
    result = block.groups(cards)
    assert result == sorted({group_of(c.topic) for c in cards})
    assert len(result) == len(set(result))
    assert result.count("hallmarks") == 1
    assert not any(g.startswith("hallmarks:") for g in result)


def test_groups_of_no_cards_is_empty():
    assert block.groups([]) == []


# --- schedule --------------------------------------------------------------------


def test_schedule_of_an_empty_store_is_empty(store):
    assert schedule(store) == {}


def test_schedule_after_saving_has_the_card_ids_and_due_times(store):
    answer_right_and_wrong(store)
    assert schedule(store) == {
        RIGHT_ID: store.box(RIGHT_ID, SKILL).due,
        WRONG_ID: store.box(WRONG_ID, SKILL).due,
    }
    assert schedule(store)[WRONG_ID] == NOW


def test_schedule_only_reads_the_recall_skill(store):
    store.record(
        AnswerRecord(
            at=NOW,
            card_id="other-card",
            skill="some-other-skill",
            mode="name",
            typed="x",
            correct=True,
            decided_by="grader",
        ),
        BoxState(
            card_id="other-card",
            skill="some-other-skill",
            box=2,
            due=NOW,
            last_seen=NOW,
            right=1,
            wrong=0,
        ),
    )
    assert schedule(store) == {}


# --- Saver -----------------------------------------------------------------------


def test_saver_right_on_new_card_goes_to_box_2_wrong_to_box_1_due_now(store):
    saver = answer_right_and_wrong(store)
    assert store.box(RIGHT_ID, SKILL).box == 2
    wrong = store.box(WRONG_ID, SKILL)
    assert wrong.box == 1
    assert wrong.due == NOW
    assert saver.saved == 2
    assert saver.unsaved == 0


def test_saver_saves_answers_under_the_recall_skill_at_now(store):
    answer_right_and_wrong(store)
    answers = store.answers()
    assert [(a.card_id, a.correct) for a in answers] == [
        (RIGHT_ID, True),
        (WRONG_ID, False),
    ]
    assert all(a.skill == "recall" for a in answers)
    assert all(a.at == NOW for a in answers)


class FlakyStore(ProgressStore):
    """A store whose file is busy for the first `fails` saves, then works."""

    def __init__(self, *args, fails, **kwargs):
        super().__init__(*args, **kwargs)
        self.fails = fails

    def record(self, answer, box=None):
        if self.fails > 0:
            self.fails -= 1
            raise ProgressFileError("the progress file is busy")
        return super().record(answer, box)


def test_saver_failure_warns_once_counts_unsaved_and_never_raises(tmp_path):
    warnings = []
    saver = Saver(
        FlakyStore(tmp_path / "progress.db", busy_seconds=0.1, fails=99),
        now=lambda: NOW,
        warn=warnings.append,
    )
    saver(attempt(card(RIGHT_ID), "telomere attrition"))  # must not raise
    assert len(warnings) == 1
    assert "progress not saved" in warnings[0]
    assert saver.unsaved == 1
    assert saver.saved == 0
    saver(attempt(card(WRONG_ID), "no idea"))  # still no raise, no second warning
    assert len(warnings) == 1
    assert saver.unsaved == 2
    assert saver.saved == 0


def test_saver_keeps_trying_and_saves_once_record_works_again(tmp_path):
    warnings = []
    flaky = FlakyStore(tmp_path / "progress.db", busy_seconds=0.1, fails=2)
    saver = Saver(flaky, now=lambda: NOW, warn=warnings.append)
    saver(attempt(card(RIGHT_ID), "telomere attrition"))
    saver(attempt(card(WRONG_ID), "no idea"))
    saver(attempt(card(RIGHT_ID), "telomere attrition"))  # the file is free now
    assert saver.saved == 1
    assert saver.unsaved == 2
    assert len(warnings) == 1
    assert [(a.card_id, a.correct) for a in flaky.answers()] == [(RIGHT_ID, True)]
    assert flaky.box(RIGHT_ID, SKILL).box == 2  # saved as a new card answered right


# --- a missed card comes back first ----------------------------------------------


def test_a_missed_card_comes_back_first(store):
    saver = Saver(store, now=lambda: NOW, warn=lambda _m: None)
    saver(attempt(card(WRONG_ID), "no idea"))
    dealt = deal(load_cards(), 3, schedule=schedule(store), now=NOW, seed=7)
    assert dealt[0].id == WRONG_ID


# --- stats_lines -----------------------------------------------------------------


def test_stats_lines_without_store_gives_total_and_one_line_per_group():
    cards = load_cards()
    lines = stats_lines(cards, None, NOW)
    assert lines[0] == f"{len(cards)} cards, all new (no progress saved yet):"
    groups = sorted({group_of(c.topic) for c in cards})
    expected = [
        f"  {g}: {sum(group_of(c.topic) == g for c in cards)} cards" for g in groups
    ]
    assert lines[1:] == expected
    hallmark_lines = [ln for ln in lines if ln.startswith("  hallmarks")]
    assert len(hallmark_lines) == 1  # writer sections + hand-made set in one group


def test_stats_lines_with_store_counts_boxes_due_and_accuracy(store):
    answer_right_and_wrong(store)
    cards = load_cards()
    lines = stats_lines(cards, store, NOW)
    text = "\n".join(lines)

    k = sum(group_of(c.topic) == "hallmarks" for c in cards)
    hallmarks = next(ln for ln in lines if ln.startswith("  hallmarks:"))
    assert hallmarks == (
        f"  hallmarks: {k} cards · new {k - 2} · box 1: 1 · box 2: 1 · due now: 1"
    )
    rapamycin = next(ln for ln in lines if ln.startswith("  rapamycin:"))
    assert "new" in rapamycin
    assert "box 1" not in rapamycin  # only boxes in use

    every = next(ln for ln in lines if ln.startswith("All:"))
    assert f"{len(cards)} cards" in every
    assert f"new {len(cards) - 2}" in every
    assert "box 1: 1" in every
    assert "box 2: 1" in every
    assert "due now: 1" in every
    assert "box 3" not in text

    assert "Last 7 days: 1 / 2 right" in lines
    missed_at = lines.index("Most missed:")
    assert lines[missed_at + 1] == f"1× {card(WRONG_ID).question}"
    assert len(lines) == missed_at + 2  # only the one missed card


def test_stats_lines_with_no_misses_has_no_most_missed(store):
    saver = Saver(store, now=lambda: NOW, warn=lambda _m: None)
    saver(attempt(card(RIGHT_ID), "telomere attrition"))
    lines = stats_lines(load_cards(), store, NOW)
    assert "Most missed:" not in lines
    assert "Last 7 days: 1 / 1 right" in lines


def test_stats_lines_now_without_timezone_raises_value_error(store):
    with pytest.raises(ValueError):
        stats_lines(load_cards(), store, datetime(2026, 11, 12, 9, 0))
