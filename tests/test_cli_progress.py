"""M4 Step 1, the CLI side: `longevity quiz` saves progress through the study block,
`--topic`, `--no-save`, `longevity stats`. The dealing / saving / counting logic is
tested in tests/blocks/test_study.py. No real keyboard, no Claude, a temp file.
"""

from datetime import UTC, datetime

import pytest

from longevity_trainer import cli
from longevity_trainer.blocks import quiz_round
from longevity_trainer.blocks.card_bank import load_cards
from longevity_trainer.blocks.study import SKILL, Saver
from quizkit.blocks.progress_store import ProgressStore

NOW = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)


def card(card_id):
    return next(c for c in load_cards() if c.id == card_id)


@pytest.fixture
def progress(tmp_path, monkeypatch):
    path = tmp_path / "progress.db"
    monkeypatch.setattr(cli, "PROGRESS_FILE", path)
    return path


def typing(monkeypatch, *replies):
    it = iter(replies)
    monkeypatch.setattr("builtins.input", lambda _prompt: next(it))


def play(cards, replies, saver):
    it = iter(replies)
    cli.play(
        cards, read=lambda _p: next(it, None), write=lambda _l: None, on_answer=saver
    )


def test_quiz_saves_answers_and_boxes(progress, monkeypatch):
    typing(monkeypatch, "", "q")  # blank = wrong, no own-mark prompt
    assert cli.main(["quiz", "--topic", "hallmarks", "--no-judge"]) == 0
    store = ProgressStore(progress)
    [answer] = store.answers()
    assert answer.skill == SKILL
    assert store.box(answer.card_id, SKILL).box == 1


def test_no_save_writes_no_progress_file(progress, monkeypatch):
    typing(monkeypatch, "q")
    assert cli.main(["quiz", "-n", "2", "--no-save", "--no-judge", "--seed", "1"]) == 0
    assert not progress.exists()


def test_unknown_topic_says_so_and_lists_topics(progress, capsys):
    assert cli.main(["quiz", "--topic", "zzz-nothing", "--no-judge"]) == 1
    out = capsys.readouterr().out
    assert "zzz-nothing" in out
    assert "rapamycin" in out


def test_default_quiz_length_is_10(progress, monkeypatch, capsys):
    typing(monkeypatch, "q")
    assert cli.main(["quiz", "--no-judge", "--seed", "1"]) == 0
    assert "10 questions" in capsys.readouterr().out


def test_unusable_progress_file_is_one_line_and_exit_1(progress, capsys):
    progress.write_text("not a database", encoding="utf-8")
    assert cli.main(["quiz", "--no-judge"]) == 1
    assert "progress.db" in capsys.readouterr().out
    assert cli.main(["stats"]) == 1


def test_quitting_at_the_own_mark_prompt_saves_nothing(progress):
    c = card("hm-telomeres-why")
    play([c], ["no telomerase in most cells"], Saver(ProgressStore(progress)))
    assert ProgressStore(progress).answers() == []  # you never marked it


def answer_everything_right(progress):
    """Save a right answer for every card: nothing is due today afterwards."""
    store = ProgressStore(progress)
    saver = Saver(store)
    for c in load_cards():
        play([c], [c.answers[0]], saver)
    return store


def test_nothing_due_says_when_next_and_asks_nothing(progress, monkeypatch, capsys):
    answer_everything_right(progress)
    monkeypatch.setattr("builtins.input", lambda _p: pytest.fail("asked a question"))
    assert cli.main(["quiz", "--no-judge"]) == 0
    out = capsys.readouterr().out
    assert "Nothing due" in out
    assert "--practise" in out


def test_practise_deals_not_due_cards_and_saves_nothing(progress, monkeypatch, capsys):
    store = answer_everything_right(progress)
    before = len(store.answers())
    typing(monkeypatch, "", "q")
    assert cli.main(["quiz", "--practise", "--no-judge", "--seed", "1"]) == 0
    assert "10 questions" in capsys.readouterr().out
    assert len(ProgressStore(progress).answers()) == before


def test_mistyped_topic_creates_no_progress_file(progress, capsys):
    assert cli.main(["quiz", "--topic", "hallmrks", "--no-judge"]) == 1
    out = capsys.readouterr().out
    assert "hallmarks" in out  # the groups you can pick
    assert "hallmarks: dysbiosis" not in out  # groups, not every sub-topic
    assert not progress.exists()


@pytest.mark.parametrize("n", ["0", "-3", "x"])
def test_bad_n_is_rejected(progress, n):
    with pytest.raises(SystemExit) as exit_:
        cli.main(["quiz", "-n", n, "--no-judge"])
    assert exit_.value.code == 2


def test_a_read_error_in_quiz_is_one_line(progress, monkeypatch, capsys):
    from quizkit.blocks.progress_store import ProgressFileError

    answer_everything_right(progress)

    def broken(_store):
        raise ProgressFileError("database is busy")

    monkeypatch.setattr(quiz_round, "schedule", broken)
    assert cli.main(["quiz", "--no-judge"]) == 1
    assert "database is busy" in capsys.readouterr().out


def test_a_read_error_in_stats_is_one_line(progress, monkeypatch, capsys):
    from quizkit.blocks.progress_store import ProgressFileError

    answer_everything_right(progress)

    def broken(*_a, **_k):
        raise ProgressFileError("a bad row")

    monkeypatch.setattr(cli, "stats_lines", broken)
    assert cli.main(["stats"]) == 1
    assert "a bad row" in capsys.readouterr().out


def test_stats_with_no_progress_creates_nothing(progress, capsys):
    assert cli.main(["stats"]) == 0
    out = capsys.readouterr().out
    assert f"{len(load_cards())} cards" in out
    assert "hallmarks:" in out and "rapamycin:" in out
    assert not progress.exists()


def test_stats_after_playing(progress, capsys):
    right, wrong = card("hm-telomeres-name"), card("hm-dysbiosis-name")
    saver = Saver(ProgressStore(progress), now=lambda: datetime.now(UTC))
    play([right, wrong], ["telomere attrition", "no idea", "n"], saver)
    assert cli.main(["stats"]) == 0
    out = capsys.readouterr().out
    assert "box 1: 1" in out and "box 2: 1" in out
    assert "due now: 1" in out
    assert "1 / 2 right" in out
    assert wrong.question[:30] in out
