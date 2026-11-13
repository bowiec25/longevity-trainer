"""Tests for the quiz_round block: its contract (ID card + SPEC.md) and its behaviour.

The behaviour tests were written from SPEC.md "How to test", before the code. They
reach the block's names through `block.<name>` (not `from ... import`), so the
contract tests still run while the code isn't built. No real Claude: a fake judge
and a fake make_judge; progress in tmp_path; a fixed, timezone-aware NOW.
"""

import dataclasses
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import longevity_trainer.blocks.quiz_round as block
from longevity_trainer.blocks.card_bank import LongevityCard, load_cards
from longevity_trainer.blocks.study import Saver, next_due, schedule
from quizkit.blocks.base import missing_spec_sections, spec_section
from quizkit.blocks.engine import QuizSession
from quizkit.blocks.progress_store import ProgressFileError, ProgressStore
from quizkit.blocks.receipts import Receipt
from quizkit.models import Verdict

SPEC_MD = Path(block.__file__).parent / "SPEC.md"
NOW = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)
QUOTE = "A word-for-word quote that is long enough to count as a receipt."


# --- contract --------------------------------------------------------------------


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "quiz_round"
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


# --- helpers ---------------------------------------------------------------------


def make_card(card_id, topic="alpha", answers=("telomere attrition",), kind="name"):
    return LongevityCard(
        id=card_id,
        kind=kind,
        topic=topic,
        question=f"What is the answer to question {card_id}?",
        answers=list(answers),
        receipt=Receipt(source="src-1", quote=QUOTE, page=3),
    )


def three_cards():
    return [
        make_card("c-1", topic="alpha: one", answers=("first answer",)),
        make_card("c-2", topic="alpha: two", answers=("second answer",)),
        make_card("c-3", topic="beta", answers=("third answer",)),
    ]


class FakeJudge:
    """Any (Question, str) -> Verdict; records what it was asked."""

    def __init__(self, correct=False, reason="not the same idea", source="claude"):
        self.verdict = Verdict(correct=correct, reason=reason, source=source)
        self.calls = []

    def __call__(self, question, typed):
        self.calls.append((question.card_id, typed))
        return self.verdict


class FakeMakeJudge:
    """Stands in for marking.make_judge; records the kwargs of each call."""

    def __init__(self, judge=None):
        self.judge = judge or FakeJudge()
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self.judge


def attempt_for(card, typed, verdict=None):
    """A real quizkit Attempt for `card`, judged by a judge giving `verdict`."""
    judge = None if verdict is None else (lambda _q, _t: verdict)
    return QuizSession([card.to_question()], judge=judge).answer(typed)


def save_answer(path, card, typed, when):
    Saver(ProgressStore(path), now=lambda: when)(attempt_for(card, typed))


@pytest.fixture
def files(tmp_path):
    return block.RoundFiles(
        progress=tmp_path / "progress.db", judge_cache=tmp_path / "cache.jsonl"
    )


def answers_saved(files):
    if not files.progress.exists():
        return []
    return ProgressStore(files.progress).answers()


# --- RoundOptions, RoundFiles, the default paths -----------------------------------


def test_round_options_defaults():
    o = block.RoundOptions()
    assert (o.topic, o.n, o.practise, o.judge, o.save, o.seed) == (
        None,
        10,
        False,
        True,
        True,
        None,
    )


@pytest.mark.parametrize("n", [0, -1])
def test_round_options_n_below_1_raises(n):
    with pytest.raises(ValueError):
        block.RoundOptions(n=n)


def test_round_options_and_files_are_frozen(files):
    with pytest.raises(dataclasses.FrozenInstanceError):
        block.RoundOptions().n = 3
    with pytest.raises(dataclasses.FrozenInstanceError):
        files.progress = Path("elsewhere.db")


def test_round_files_reads_the_module_paths_when_built(tmp_path, monkeypatch):
    monkeypatch.setattr(block, "PROGRESS_FILE", tmp_path / "late.db")
    monkeypatch.setattr(block, "JUDGE_CACHE", tmp_path / "late.jsonl")
    f = block.RoundFiles()
    assert f.progress == tmp_path / "late.db"
    assert f.judge_cache == tmp_path / "late.jsonl"


def test_default_paths_are_gitignored_data_files():
    """conftest points them at temp files; their names still match the SPEC."""
    assert isinstance(block.PROGRESS_FILE, Path)
    assert isinstance(block.JUDGE_CACHE, Path)
    assert block.PROGRESS_FILE.name.endswith(".db")
    assert block.JUDGE_CACHE.name.endswith(".jsonl")


# --- wording -----------------------------------------------------------------------


def test_self_verdicts_and_own_mark_question():
    assert block.SELF_YES == Verdict(
        correct=True, reason="you marked it right", source="self"
    )
    assert block.SELF_NO == Verdict(
        correct=False, reason="you marked it wrong", source="self"
    )
    assert block.OWN_MARK_QUESTION == "Count it as right?"


def test_feedback_right_by_the_answer_list():
    c = make_card("c")
    assert block.feedback(attempt_for(c, "telomere attrition"), c) == ["✓ Right"]


def test_feedback_typo_forgiven_is_right_by_the_list():
    c = make_card("c")
    assert block.feedback(attempt_for(c, "telomere atrition"), c) == ["✓ Right"]


@pytest.mark.parametrize("source", ["claude", "cache"])
def test_feedback_right_by_claude_shows_the_model_answer(source):
    c = make_card("c", answers=("telomere attrition", "telomere shortening"))
    yes = Verdict(correct=True, reason="same idea", source=source)
    assert block.feedback(attempt_for(c, "ends get shorter", yes), c) == [
        "✓ Right (Claude: same idea)",
        "Model answer: telomere attrition",
    ]


def test_feedback_wrong_by_claude():
    c = make_card("c")
    no = Verdict(correct=False, reason="that's a different hallmark", source="claude")
    assert block.feedback(attempt_for(c, "senescence", no), c) == [
        "✗ Claude: that's a different hallmark",
        "Answer: telomere attrition",
    ]


def test_feedback_wrong_and_claude_couldnt_check():
    c = make_card("c")
    unchecked = Verdict(correct=False, reason="Claude is offline", source="not_checked")
    assert block.feedback(attempt_for(c, "senescence", unchecked), c) == [
        "(Claude: Claude is offline)",
        "Answer: telomere attrition",
    ]


def test_feedback_wrong_and_not_asked():
    c = make_card("c")
    assert block.feedback(attempt_for(c, "senescence"), c) == [
        "Answer: telomere attrition"
    ]


def test_feedback_blank_answer_is_just_the_answer():
    c = make_card("c")
    assert block.feedback(attempt_for(c, ""), c) == ["Answer: telomere attrition"]


def test_own_mark_line_and_not_this_time():
    assert block.own_mark_line(True) == "✓ Counted"
    assert block.own_mark_line(False) == "✗ Not this time"
    assert block.NOT_THIS_TIME == "✗ Not this time"


def test_receipt_line():
    c = make_card("c")
    assert block.receipt_line(c) == f'Receipt: "{QUOTE}" (src-1, p. 3)'


def test_receipt_line_on_a_real_card():
    c = load_cards()[0]
    r = c.receipt
    assert block.receipt_line(c) == f'Receipt: "{r.quote}" ({r.source}, p. {r.page})'


def test_score_line():
    cards = three_cards()
    session = QuizSession([c.to_question() for c in cards])
    session.answer("first answer")
    session.answer("wrong")
    assert block.score_line(session.result()) == "Score: 1 / 2"


# --- setup: dealing ----------------------------------------------------------------


def due_later_and_new(files):
    """c-1 due now (answered wrong), c-2 due tomorrow (answered right), c-3 new."""
    cards = three_cards()
    save_answer(files.progress, cards[0], "wrong", NOW - timedelta(days=10))
    save_answer(files.progress, cards[1], "second answer", NOW)
    return cards


def test_setup_deals_due_then_new(files):
    cards = due_later_and_new(files)
    r = block.setup(block.RoundOptions(seed=1, judge=False), files, bank=cards, now=NOW)
    assert [c.id for c in r.cards] == ["c-1", "c-3"]


def test_setup_returns_a_frozen_round_with_a_saver(files):
    cards = three_cards()
    r = block.setup(block.RoundOptions(seed=1, judge=False), files, bank=cards, now=NOW)
    assert isinstance(r.saver, Saver)
    assert r.judge is None
    assert files.progress.exists()  # created now that a quiz starts
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.cards = []


def test_setup_deals_at_most_n_and_by_topic(files):
    cards = three_cards()
    r = block.setup(block.RoundOptions(n=1, judge=False), files, bank=cards, now=NOW)
    assert len(r.cards) == 1
    r = block.setup(
        block.RoundOptions(topic="alpha", judge=False), files, bank=cards, now=NOW
    )
    assert {c.id for c in r.cards} == {"c-1", "c-2"}


def test_setup_with_a_seed_deals_the_same_order(files):
    cards = load_cards()
    opts = block.RoundOptions(n=5, seed=7, judge=False, save=False)
    first = block.setup(opts, files, bank=cards, now=NOW)
    again = block.setup(opts, files, bank=cards, now=NOW)
    assert [c.id for c in first.cards] == [c.id for c in again.cards]


def test_practise_deals_not_due_cards_and_gives_no_saver(files):
    cards = due_later_and_new(files)
    before = len(answers_saved(files))
    r = block.setup(
        block.RoundOptions(practise=True, seed=1, judge=False),
        files,
        bank=cards,
        now=NOW,
    )
    assert {c.id for c in r.cards} == {"c-1", "c-2", "c-3"}
    assert r.saver is None
    assert len(answers_saved(files)) == before


def test_practise_creates_no_progress_file(files):
    r = block.setup(
        block.RoundOptions(practise=True, judge=False),
        files,
        bank=three_cards(),
        now=NOW,
    )
    assert r.saver is None
    assert not files.progress.exists()


def test_save_false_gives_no_saver_and_no_file(files):
    r = block.setup(
        block.RoundOptions(save=False, judge=False), files, bank=three_cards(), now=NOW
    )
    assert r.saver is None
    assert r.cards
    assert not files.progress.exists()


def test_bank_defaults_to_the_card_bank(files):
    r = block.setup(block.RoundOptions(n=3, judge=False, save=False), files, now=NOW)
    real_ids = {c.id for c in load_cards()}
    assert len(r.cards) == 3
    assert {c.id for c in r.cards} <= real_ids


def test_the_saver_warns_into_warn(files):
    warnings = []
    cards = three_cards()
    r = block.setup(
        block.RoundOptions(judge=False),
        files,
        bank=cards,
        now=NOW,
        warn=warnings.append,
    )
    files.progress.write_text("not a database", encoding="utf-8")
    r.saver(attempt_for(cards[0], "first answer"))
    r.saver(attempt_for(cards[1], "second answer"))
    assert len(warnings) == 1
    assert "progress not saved" in warnings[0]


# --- setup: the judge ----------------------------------------------------------------


def test_judge_false_never_calls_make_judge(files):
    make = FakeMakeJudge()
    r = block.setup(
        block.RoundOptions(judge=False),
        files,
        bank=three_cards(),
        now=NOW,
        make_judge=make,
    )
    assert make.calls == []
    assert r.judge is None


def test_judge_is_built_with_the_cache_and_before_asking(files):
    make = FakeMakeJudge()

    def hook():
        return None

    r = block.setup(
        block.RoundOptions(),
        files,
        bank=three_cards(),
        now=NOW,
        make_judge=make,
        before_asking=hook,
    )
    assert make.calls == [{"cache_file": files.judge_cache, "before_asking": hook}]
    c = r.cards[0]
    r.judge(c.to_question(), "something")
    assert make.judge.calls == [(c.id, "something")]


def test_a_make_judge_that_raises_is_not_caught(files):
    def broken(**_kwargs):
        raise RuntimeError("a bug")

    with pytest.raises(RuntimeError, match="a bug"):
        block.setup(
            block.RoundOptions(), files, bank=three_cards(), now=NOW, make_judge=broken
        )


# --- setup: failure modes -------------------------------------------------------------


def all_answered_right(files, cards):
    for c in cards:
        save_answer(files.progress, c, c.answers[0], NOW)


def expected_nothing_due(files, cards, hint):
    soonest = next_due(cards, schedule(ProgressStore(files.progress)))
    when = soonest.astimezone().strftime("%a %d %b %H:%M")
    return f"Nothing due. Next card due {when}. ({hint} to review anyway)"


def test_nothing_due_says_when_next_with_the_hint(files):
    cards = three_cards()
    all_answered_right(files, cards)
    with pytest.raises(block.SetupProblem) as problem:
        block.setup(block.RoundOptions(judge=False), files, bank=cards, now=NOW)
    assert problem.value.nothing_due is True
    assert problem.value.lines == [expected_nothing_due(files, cards, "--practise")]


def test_nothing_due_uses_the_screens_hint(files):
    cards = three_cards()
    all_answered_right(files, cards)
    with pytest.raises(block.SetupProblem) as problem:
        block.setup(
            block.RoundOptions(judge=False),
            files,
            bank=cards,
            now=NOW,
            practise_hint="turn on Practise",
        )
    assert problem.value.lines == [
        expected_nothing_due(files, cards, "turn on Practise")
    ]


def test_nothing_due_only_counts_cards_on_the_topic(files):
    cards = three_cards()
    all_answered_right(files, cards[:2])  # alpha all done, beta still new
    with pytest.raises(block.SetupProblem) as problem:
        block.setup(
            block.RoundOptions(topic="alpha", judge=False), files, bank=cards, now=NOW
        )
    assert problem.value.nothing_due is True
    r = block.setup(
        block.RoundOptions(topic="beta", judge=False), files, bank=cards, now=NOW
    )
    assert [c.id for c in r.cards] == ["c-3"]


def test_unknown_topic_lists_groups_and_creates_no_file(files):
    with pytest.raises(block.SetupProblem) as problem:
        block.setup(block.RoundOptions(topic="zzz"), files, bank=three_cards(), now=NOW)
    assert problem.value.lines == [
        "no cards on a topic containing 'zzz'. Topics:",
        "  alpha",
        "  beta",
    ]
    assert problem.value.nothing_due is False
    assert not files.progress.exists()


def test_unknown_topic_never_builds_the_judge(files):
    make = FakeMakeJudge()
    with pytest.raises(block.SetupProblem):
        block.setup(
            block.RoundOptions(topic="zzz"),
            files,
            bank=three_cards(),
            now=NOW,
            make_judge=make,
        )
    assert make.calls == []


def test_empty_bank_says_so(files):
    with pytest.raises(block.SetupProblem) as problem:
        block.setup(block.RoundOptions(judge=False), files, bank=[], now=NOW)
    assert problem.value.lines == ["no cards in the bank"]
    assert problem.value.nothing_due is False
    assert not files.progress.exists()


def test_a_progress_file_that_cant_be_opened(files):
    files.progress.write_text("not a database", encoding="utf-8")
    with pytest.raises(block.SetupProblem) as problem:
        block.setup(block.RoundOptions(judge=False), files, bank=three_cards(), now=NOW)
    [line] = problem.value.lines
    assert line.startswith("can't use progress.db: ")
    assert problem.value.nothing_due is False


def test_the_file_name_shown_is_the_files_own(tmp_path):
    files = block.RoundFiles(
        progress=tmp_path / "mine.db", judge_cache=tmp_path / "c.jsonl"
    )
    files.progress.write_text("not a database", encoding="utf-8")
    with pytest.raises(block.SetupProblem) as problem:
        block.setup(block.RoundOptions(judge=False), files, bank=three_cards(), now=NOW)
    assert problem.value.lines[0].startswith("can't use mine.db: ")


def test_a_progress_file_that_cant_be_read(files, monkeypatch):
    cards = three_cards()
    all_answered_right(files, cards)

    def broken(_store):
        raise ProgressFileError("database is busy")

    monkeypatch.setattr(block, "schedule", broken)
    with pytest.raises(block.SetupProblem) as problem:
        block.setup(block.RoundOptions(judge=False), files, bank=cards, now=NOW)
    assert problem.value.lines == ["can't read progress.db: database is busy"]
    assert problem.value.nothing_due is False


def test_a_progress_file_that_cant_be_created(files, monkeypatch):
    """Assumes the block calls quizkit's ProgressStore by that name."""

    def cant_create(*_a, **_k):
        raise ProgressFileError("disk full")

    monkeypatch.setattr(block, "ProgressStore", cant_create)
    with pytest.raises(block.SetupProblem) as problem:
        block.setup(block.RoundOptions(judge=False), files, bank=three_cards(), now=NOW)
    assert problem.value.lines == ["can't use progress.db: disk full"]
    assert problem.value.nothing_due is False


def test_setup_problem_is_an_exception():
    assert issubclass(block.SetupProblem, Exception)


# --- QuizScreen ----------------------------------------------------------------------


def screen_for(files, cards, make_judge=None, now=NOW):
    return block.QuizScreen(
        files=files,
        bank=cards,
        make_judge=make_judge or FakeMakeJudge(),
        now=lambda: now,
    )


def started(files, cards, make_judge=None, **options):
    screen = screen_for(files, cards, make_judge)
    options = {"seed": 1, "judge": False} | options
    screen.start(block.RoundOptions(**options))
    return screen


def card_of(screen, cards):
    return next(c for c in cards if c.id == screen.view.card_id)


def test_a_new_screen_is_in_setup(files):
    screen = screen_for(files, three_cards())
    assert screen.phase == "setup"
    assert screen.view is None
    assert screen.marking is None
    assert screen.result is None
    assert screen.problems == []
    assert screen.nothing_due is False


def test_start_shows_the_first_question(files):
    cards = three_cards()
    screen = started(files, cards)
    assert screen.phase == "asking"
    v = screen.view
    c = card_of(screen, cards)
    assert (v.number, v.total) == (1, 3)
    assert v.question == c.question
    assert v.topic == c.topic


def test_reading_never_moves_the_quiz_on(files):
    screen = started(files, three_cards())
    first = screen.view
    for _ in range(3):
        _ = screen.view, screen.marking, screen.result, screen.summary
    assert screen.view == first
    assert screen.phase == "asking"


def test_a_full_round_right_and_wrong_to_ended(files):
    cards = three_cards()[:2]
    screen = started(files, cards)

    c = card_of(screen, cards)
    screen.submit(c.answers[0], c.id)
    assert screen.phase == "result"
    res = screen.result
    assert (res.card_id, res.typed, res.right) == (c.id, c.answers[0], True)
    assert res.lines == ["✓ Right"]
    assert res.warning is None
    assert len(answers_saved(files)) == 1  # saved the moment it's final

    screen.next(c.id)
    assert screen.phase == "asking"
    assert screen.view.number == 2
    c = card_of(screen, cards)
    screen.submit("", c.id)  # blank: wrong, can't take your mark
    assert screen.phase == "result"
    assert screen.result.right is False
    assert screen.result.lines == [f"Answer: {c.answers[0]}", block.NOT_THIS_TIME]
    assert len(answers_saved(files)) == 2

    screen.next(c.id)
    assert screen.phase == "ended"
    assert screen.summary == ["Score: 1 / 2", "2 answers saved"]


def test_the_result_carries_the_cards_receipt(files):
    cards = three_cards()
    screen = started(files, cards)
    c = card_of(screen, cards)
    screen.submit("anything", c.id)
    if screen.phase == "own_mark":
        screen.mark(False, c.id)
    r = screen.result.receipt
    assert (r.quote, r.source, r.page) == (QUOTE, "src-1", 3)


@pytest.mark.parametrize("got_it", [True, False])
def test_own_mark_lands_in_the_result_and_is_saved(files, got_it):
    cards = three_cards()
    screen = started(files, cards)
    c = card_of(screen, cards)
    screen.submit("not it at all", c.id)
    assert screen.phase == "own_mark"
    m = screen.marking
    assert (m.card_id, m.typed) == (c.id, "not it at all")
    assert m.lines == [f"Answer: {c.answers[0]}"]
    assert m.question == block.OWN_MARK_QUESTION
    assert answers_saved(files) == []  # not final yet

    screen.mark(got_it, c.id)
    assert screen.phase == "result"
    assert screen.result.right is got_it
    assert screen.result.lines == [
        f"Answer: {c.answers[0]}",
        block.own_mark_line(got_it),
    ]
    [saved] = answers_saved(files)
    assert (saved.card_id, saved.correct) == (c.id, got_it)


def test_claude_says_no_is_final_and_not_markable(files):
    cards = three_cards()
    make = FakeMakeJudge(FakeJudge(correct=False, reason="different idea"))
    screen = started(files, cards, make, judge=True)
    c = card_of(screen, cards)
    screen.submit("a guess", c.id)
    assert screen.phase == "result"
    assert screen.result.lines == [
        "✗ Claude: different idea",
        f"Answer: {c.answers[0]}",
        block.NOT_THIS_TIME,
    ]
    assert len(answers_saved(files)) == 1


def test_claude_says_yes_shows_the_model_answer(files):
    cards = three_cards()
    make = FakeMakeJudge(FakeJudge(correct=True, reason="same idea"))
    screen = started(files, cards, make, judge=True)
    c = card_of(screen, cards)
    screen.submit("the same in other words", c.id)
    assert screen.phase == "result"
    assert screen.result.right is True
    assert screen.result.lines == [
        "✓ Right (Claude: same idea)",
        f"Model answer: {c.answers[0]}",
    ]


def test_claude_couldnt_check_asks_for_your_mark(files):
    cards = three_cards()
    make = FakeMakeJudge(
        FakeJudge(correct=False, reason="offline", source="not_checked")
    )
    screen = started(files, cards, make, judge=True)
    c = card_of(screen, cards)
    screen.submit("a guess", c.id)
    assert screen.phase == "own_mark"
    assert screen.marking.lines == ["(Claude: offline)", f"Answer: {c.answers[0]}"]


def test_the_screens_judge_has_no_before_asking(files):
    make = FakeMakeJudge()
    started(files, three_cards(), make, judge=True)
    assert make.calls == [{"cache_file": files.judge_cache, "before_asking": None}]


def test_stop_in_own_mark_saves_nothing(files):
    cards = three_cards()
    screen = started(files, cards)
    c = card_of(screen, cards)
    screen.submit("not it", c.id)
    assert screen.phase == "own_mark"
    screen.stop()
    assert screen.phase == "ended"
    assert answers_saved(files) == []


def test_stop_while_asking_ends_the_quiz(files):
    screen = started(files, three_cards())
    screen.stop()
    assert screen.phase == "ended"


def test_practise_summary_and_nothing_saved(files):
    cards = three_cards()[:1]
    screen = started(files, cards, practise=True)
    c = card_of(screen, cards)
    screen.submit(c.answers[0], c.id)
    screen.next(c.id)
    assert screen.phase == "ended"
    assert screen.summary == ["Score: 1 / 1", "Practise: nothing saved"]
    assert not files.progress.exists()


def test_no_save_summary_is_just_the_score(files):
    cards = three_cards()[:1]
    screen = started(files, cards, save=False)
    c = card_of(screen, cards)
    screen.submit(c.answers[0], c.id)
    screen.next(c.id)
    assert screen.summary == ["Score: 1 / 1"]
    assert not files.progress.exists()


def test_a_save_failure_shows_warning_once(files):
    cards = three_cards()[:2]
    screen = started(files, cards)
    files.progress.write_text("not a database", encoding="utf-8")

    c = card_of(screen, cards)
    screen.submit(c.answers[0], c.id)
    assert screen.phase == "result"
    assert screen.result.warning
    assert "progress not saved" in screen.result.warning
    screen.next(c.id)

    c = card_of(screen, cards)
    screen.submit(c.answers[0], c.id)
    assert screen.result.warning is None  # only the first failure warns
    screen.next(c.id)
    assert screen.summary == [
        "Score: 2 / 2",
        "0 answers saved",
        "2 answers not saved",
    ]


def test_start_reads_now_for_what_is_due(files):
    """c-2 is due tomorrow: not dealt today, dealt two days later."""
    cards = due_later_and_new(files)
    today = started(files, cards)
    assert today.view.total == 2
    later = screen_for(files, cards, now=NOW + timedelta(days=2))
    later.start(block.RoundOptions(seed=1, judge=False))
    assert later.view.total == 3


def test_saving_uses_the_screens_now(files):
    cards = three_cards()
    screen = started(files, cards)
    c = card_of(screen, cards)
    screen.submit(c.answers[0], c.id)
    [saved] = answers_saved(files)
    assert saved.at == NOW


# --- QuizScreen: stale and double clicks -----------------------------------------------


def snapshot(screen):
    return (
        screen.phase,
        screen.view,
        screen.marking,
        screen.result,
        list(screen.summary),
    )


def test_submit_naming_another_card_does_nothing(files):
    screen = started(files, three_cards())
    before = snapshot(screen)
    screen.submit("first answer", "not-the-current-card")
    assert snapshot(screen) == before
    assert answers_saved(files) == []


def test_double_submit_does_nothing_the_second_time(files):
    cards = three_cards()
    screen = started(files, cards)
    c = card_of(screen, cards)
    screen.submit(c.answers[0], c.id)
    before = snapshot(screen)
    screen.submit("something else", c.id)
    assert snapshot(screen) == before
    assert len(answers_saved(files)) == 1


def test_double_mark_does_nothing_the_second_time(files):
    cards = three_cards()
    screen = started(files, cards)
    c = card_of(screen, cards)
    screen.submit("not it", c.id)
    screen.mark(True, c.id)
    before = snapshot(screen)
    screen.mark(False, c.id)
    assert snapshot(screen) == before
    assert len(answers_saved(files)) == 1


def test_mark_with_the_wrong_card_or_phase_does_nothing(files):
    cards = three_cards()
    screen = started(files, cards)
    c = card_of(screen, cards)
    before = snapshot(screen)
    screen.mark(True, c.id)  # asking: nothing to mark
    assert snapshot(screen) == before
    screen.submit("not it", c.id)
    before = snapshot(screen)
    screen.mark(True, "not-the-current-card")
    assert snapshot(screen) == before
    assert answers_saved(files) == []


def test_late_next_with_an_old_card_does_nothing(files):
    cards = three_cards()
    screen = started(files, cards)
    first = card_of(screen, cards)
    screen.submit(first.answers[0], first.id)
    screen.next(first.id)
    before = snapshot(screen)
    screen.next(first.id)  # a double click on "Next"
    assert snapshot(screen) == before
    assert screen.view.number == 2


def test_next_while_asking_does_nothing(files):
    cards = three_cards()
    screen = started(files, cards)
    c = card_of(screen, cards)
    before = snapshot(screen)
    screen.next(c.id)
    assert snapshot(screen) == before


def test_start_while_asking_does_nothing(files):
    screen = started(files, three_cards())
    before = snapshot(screen)
    screen.start(block.RoundOptions(topic="beta", judge=False))
    assert snapshot(screen) == before


def test_clicks_after_ended_do_nothing(files):
    cards = three_cards()
    screen = started(files, cards)
    c = card_of(screen, cards)
    screen.stop()
    before = snapshot(screen)
    screen.submit(c.answers[0], c.id)
    screen.mark(True, c.id)
    screen.next(c.id)
    assert snapshot(screen) == before
    assert answers_saved(files) == []


# --- QuizScreen: failed start, new quiz ---------------------------------------------


def test_a_failed_start_shows_problems_and_stays_in_setup(files):
    screen = screen_for(files, three_cards())
    screen.start(block.RoundOptions(topic="zzz", judge=False))
    assert screen.phase == "setup"
    assert screen.problems == [
        "no cards on a topic containing 'zzz'. Topics:",
        "  alpha",
        "  beta",
    ]
    assert screen.nothing_due is False
    assert screen.view is None


def test_nothing_due_start_uses_the_web_hint(files):
    cards = three_cards()
    all_answered_right(files, cards)
    screen = screen_for(files, cards)
    screen.start(block.RoundOptions(judge=False))
    assert screen.phase == "setup"
    assert screen.nothing_due is True
    assert screen.problems == [expected_nothing_due(files, cards, "turn on Practise")]


def test_an_unusable_file_start_shows_one_problem(files):
    files.progress.write_text("not a database", encoding="utf-8")
    screen = screen_for(files, three_cards())
    screen.start(block.RoundOptions(judge=False))
    assert screen.phase == "setup"
    [line] = screen.problems
    assert line.startswith("can't use progress.db: ")


def test_a_good_start_after_a_failed_one_clears_problems(files):
    screen = screen_for(files, three_cards())
    screen.start(block.RoundOptions(topic="zzz", judge=False))
    screen.start(block.RoundOptions(topic="beta", judge=False))
    assert screen.phase == "asking"
    assert screen.problems == []
    assert screen.nothing_due is False


def test_new_quiz_goes_back_to_setup_and_can_start_again(files):
    cards = three_cards()
    screen = started(files, cards)
    screen.stop()
    screen.new_quiz()
    assert screen.phase == "setup"
    assert screen.view is None
    assert screen.result is None
    screen.start(block.RoundOptions(seed=1, judge=False, save=False))
    assert screen.phase == "asking"
    assert screen.view.number == 1


def test_start_from_ended_starts_a_new_round(files):
    """SPEC: start works in setup or ended."""
    screen = started(files, three_cards(), save=False)
    screen.stop()
    screen.start(block.RoundOptions(topic="beta", judge=False, save=False))
    assert screen.phase == "asking"
    assert screen.view.total == 1


# --- SPEC update: stop's summary, setup's clock, the own-mark rule -------------------


def test_stop_at_own_mark_counts_it_answered_but_unsaved(files):
    cards = three_cards()
    screen = started(files, cards)
    c = card_of(screen, cards)
    screen.submit("not it", c.id)
    assert screen.phase == "own_mark"
    screen.stop()
    assert screen.summary == ["Score: 0 / 1", "0 answers saved"]
    assert answers_saved(files) == []


def test_stop_from_result_keeps_the_saved_answer(files):
    cards = three_cards()
    screen = started(files, cards)
    c = card_of(screen, cards)
    screen.submit(c.answers[0], c.id)
    assert screen.phase == "result"
    screen.stop()
    assert screen.phase == "ended"
    assert screen.summary == ["Score: 1 / 1", "1 answers saved"]
    [saved] = answers_saved(files)
    assert saved.card_id == c.id


def test_setup_saver_stamps_answers_with_clock(files):
    cards = three_cards()
    stamp = NOW + timedelta(hours=5)
    r = block.setup(
        block.RoundOptions(judge=False),
        files,
        bank=cards,
        now=NOW,
        clock=lambda: stamp,
    )
    r.saver(attempt_for(cards[0], "first answer"))
    [saved] = answers_saved(files)
    assert saved.at == stamp


def test_setup_saver_without_clock_uses_the_real_time(files):
    cards = three_cards()
    r = block.setup(block.RoundOptions(judge=False), files, bank=cards, now=NOW)
    before = datetime.now(UTC)
    r.saver(attempt_for(cards[0], "first answer"))
    after = datetime.now(UTC)
    [saved] = answers_saved(files)
    assert before <= saved.at <= after


@pytest.mark.parametrize(
    ("typed", "verdict"),
    [
        ("first answer", None),  # right by the list
        ("first answr", None),  # typo forgiven
        ("not it", None),  # wrong, nobody asked
        ("", None),  # blank
        ("   ", None),  # only spaces
        ("not it", Verdict(correct=False, reason="no", source="claude")),
        ("not it", Verdict(correct=True, reason="yes", source="claude")),
        ("not it", Verdict(correct=False, reason="offline", source="not_checked")),
        ("", Verdict(correct=False, reason="offline", source="not_checked")),
    ],
)
def test_own_mark_phase_is_exactly_can_own_mark(files, typed, verdict):
    cards = three_cards()[:1]
    c = cards[0]
    judge = FakeJudge()
    if verdict is not None:
        judge.verdict = verdict
    make = FakeMakeJudge(judge)
    screen = started(files, cards, make, judge=verdict is not None)

    session = QuizSession(
        [c.to_question()], judge=None if verdict is None else (lambda _q, _t: verdict)
    )
    session.answer(typed)

    screen.submit(typed, c.id)
    assert (screen.phase == "own_mark") is session.can_own_mark
    assert screen.phase == ("own_mark" if session.can_own_mark else "result")
