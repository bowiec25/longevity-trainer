"""`longevity quiz`: fake typing in, collected lines out. No real keyboard, no Claude."""

from longevity_trainer.blocks.card_bank import load_cards
from longevity_trainer.cli import main, play


def card(card_id):
    return next(c for c in load_cards() if c.id == card_id)


def run(cards, typed):
    replies = iter(typed)
    lines = []
    score = play(cards, read=lambda _prompt: next(replies, None), write=lines.append)
    return score, "\n".join(lines)


def test_right_answer_scores_and_shows_receipt():
    score, out = run([card("hm-telomeres-name")], ["telomere attrition"])
    assert score == (1, 1)
    assert "✓ Right" in out
    assert "Receipt:" in out and "p. 9" in out


def test_small_typo_is_forgiven():
    score, _ = run([card("hm-dysbiosis-name")], ["dysbiosys"])
    assert score == (1, 1)


def test_wrong_answer_shows_the_answer_and_takes_own_mark():
    score, out = run([card("hm-telomeres-why")], ["no telomerase in most cells", "y"])
    assert score == (1, 1)
    assert "Answer: Most body" in out
    assert "✓ Counted" in out


def test_own_mark_no_stays_wrong():
    score, _ = run([card("hm-telomeres-why")], ["no idea", "n"])
    assert score == (0, 1)


def test_blank_answer_is_wrong_without_asking():
    score, out = run([card("hm-dysbiosis-name"), card("hm-il6-marker")], ["", "IL-6"])
    assert score == (1, 2)
    assert "Count it as right" not in out


def test_q_quits_and_keeps_the_score():
    cards = [card("hm-dysbiosis-name"), card("hm-il6-marker")]
    score, out = run(cards, ["dysbiosis", "q"])
    assert score == (1, 1)
    assert "Score: 1 / 1" in out


def test_main_runs_n_questions(monkeypatch, capsys):
    replies = iter(["q"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(replies))
    assert main(["quiz", "-n", "2", "--seed", "1"]) == 0
    assert "Score: 0 / 0" in capsys.readouterr().out


def fake_judge(correct, source="claude", reason="gets the key idea"):
    from quizkit.models import Verdict

    calls = []

    def judge(question, typed):
        calls.append((question.mode, typed))
        return Verdict(correct=correct, reason=reason, source=source)

    judge.calls = calls
    return judge


def run_judged(cards, typed, judge):
    replies = iter(typed)
    lines = []
    score = play(
        cards, read=lambda _p: next(replies, None), write=lines.append, judge=judge
    )
    return score, "\n".join(lines)


def test_claude_accepts_an_open_answer():
    judge = fake_judge(True)
    score, out = run_judged(
        [card("hm-telomeres-why")], ["cells lack telomerase"], judge
    )
    assert score == (1, 1)
    assert "Claude: gets the key idea" in out
    assert "Count it as right" not in out  # Claude checked it: no own mark
    assert judge.calls == [("explain", "cells lack telomerase")]  # kind is the mode


def test_claude_rejects_and_says_why():
    score, out = run_judged(
        [card("hm-telomeres-why")],
        ["too much sugar"],
        fake_judge(False, reason="wrong"),
    )
    assert score == (0, 1)
    assert "✗ Claude: wrong" in out and "Answer: Most body" in out


def test_answer_list_hit_never_asks_claude():
    judge = fake_judge(False)
    score, _ = run_judged([card("hm-dysbiosis-name")], ["dysbiosis"], judge)
    assert score == (1, 1) and judge.calls == []


def test_claude_unreachable_falls_back_to_own_mark():
    judge = fake_judge(False, source="not_checked", reason="couldn't check: offline")
    score, out = run_judged([card("hm-telomeres-why")], ["no telomerase", "y"], judge)
    assert score == (1, 1)
    assert "(Claude: couldn't check: offline)" in out and "Counted" in out
