"""The web pages (ADR 0009), run in-process by Streamlit's AppTest (no browser).

The pages are thin, so these check the wiring: the buttons reach `QuizScreen`, and
each screen shows what it says. The rules themselves are tested in
tests/blocks/test_quiz_round.py. No real Claude, temp progress files.
"""

import re

from streamlit.testing.v1 import AppTest

from longevity_trainer import cli
from longevity_trainer.blocks.card_bank import ROOT, load_cards
from longevity_trainer.blocks.quiz_round import QuizScreen, RoundFiles
from quizkit.blocks.progress_store import ProgressStore
from quizkit.models import Verdict

COULDNT = Verdict(correct=False, reason="offline", source="not_checked")
SAYS_NO = Verdict(correct=False, reason="misses the key idea", source="claude")


def card(card_id):
    return next(c for c in load_cards() if c.id == card_id)


def judge_saying(verdict):
    def make_judge(**_kwargs):
        return lambda question, typed: verdict

    return make_judge


def page(tmp_path, cards=("hm-telomeres-name",), verdict=COULDNT):
    files = RoundFiles(
        progress=tmp_path / "progress.db", judge_cache=tmp_path / "cache.jsonl"
    )
    at = AppTest.from_file(str(cli.WEB_PAGE), default_timeout=30)
    at.session_state["quiz"] = QuizScreen(
        files=files,
        bank=[card(c) for c in cards],
        make_judge=judge_saying(verdict),
    )
    at.run()
    return at


def button(at, label):
    return next(b for b in at.button if b.label == label)


def shown(text):
    """As the browser shows it: the page escapes Markdown with backslashes."""
    return re.sub(r"\\(.)", r"\1", text)


def texts(at):
    return shown(
        " | ".join(
            [e.value for e in at.markdown]
            + [e.value for e in at.caption]
            + [e.value for e in at.text]
            + [e.value for e in at.success]
            + [e.value for e in at.error]
            + [e.value for e in at.info]
            + [e.value for e in at.warning]
        )
    )


def answer(at, typed):
    at.text_area[0].input(typed)
    button(at, "Check").click().run()


def test_page_opens_on_the_settings(tmp_path):
    at = page(tmp_path)
    assert not at.exception
    assert "Start quiz" in [b.label for b in at.button]
    assert "hallmarks" in at.selectbox(key="topic").options


def test_a_right_answer_shows_the_receipt_and_is_saved(tmp_path):
    at = page(tmp_path)
    at.button(key="start").click().run()
    assert "Question 1 of 1" in [s.value for s in at.subheader]
    answer(at, card("hm-telomeres-name").answers[0])
    assert not at.exception
    assert "✓ Right" in texts(at)
    assert card("hm-telomeres-name").receipt.quote in texts(at)
    assert len(ProgressStore(tmp_path / "progress.db").answers()) == 1
    button(at, "Next →").click().run()
    assert "Score: 1 / 1" in texts(at)
    assert "1 answers saved" in texts(at)


def test_claude_offline_asks_for_your_own_mark(tmp_path):
    at = page(tmp_path, verdict=COULDNT)
    at.button(key="start").click().run()
    answer(at, "something else entirely")
    assert "Count it as right?" in texts(at)
    assert "(Claude: offline)" in texts(at)
    button(at, "Yes").click().run()
    assert "✓ Counted" in texts(at)
    assert ProgressStore(tmp_path / "progress.db").answers()[0].correct


def test_claude_saying_no_shows_why_and_the_answer(tmp_path):
    at = page(tmp_path, verdict=SAYS_NO)
    at.button(key="start").click().run()
    answer(at, "something else entirely")
    out = texts(at)
    assert "✗ Claude: misses the key idea" in out
    assert f"Answer: {card('hm-telomeres-name').answers[0]}" in out
    assert "✗ Not this time" in out


def test_stop_ends_the_quiz_and_new_quiz_goes_back(tmp_path):
    at = page(tmp_path, cards=("hm-telomeres-name", "hm-dysbiosis-name"))
    at.button(key="start").click().run()
    at.button(key="stop").click().run()
    assert "Done" in [s.value for s in at.subheader]
    at.button(key="new").click().run()
    assert "Start quiz" in [b.label for b in at.button]


def test_nothing_due_says_turn_on_practise(tmp_path):
    at = page(tmp_path)
    at.button(key="start").click().run()
    answer(at, card("hm-telomeres-name").answers[0])
    button(at, "Next →").click().run()
    at.button(key="new").click().run()
    at.button(key="start").click().run()
    out = texts(at)
    assert "Nothing due" in out and "turn on Practise" in out


def test_a_bad_progress_file_is_shown_not_a_crash(tmp_path):
    (tmp_path / "progress.db").write_text("not a database", encoding="utf-8")
    at = page(tmp_path)
    at.button(key="start").click().run()
    assert not at.exception
    assert "progress.db" in texts(at)


def test_stats_page_shows_the_stats_lines(tmp_path):
    at = page(tmp_path)
    at.button(key="start").click().run()
    answer(at, card("hm-telomeres-name").answers[0])
    stats = AppTest.from_file(
        str(cli.WEB_PAGE.with_name("web_pages") / "stats.py"), default_timeout=30
    )
    stats.session_state["quiz"] = at.session_state["quiz"]
    stats.run()
    assert not stats.exception
    out = texts(stats)
    assert "box 2: 1" in out


def test_stats_page_with_a_bad_progress_file_says_so(tmp_path):
    (tmp_path / "progress.db").write_text("not a database", encoding="utf-8")
    stats = AppTest.from_file(
        str(cli.WEB_PAGE.with_name("web_pages") / "stats.py"), default_timeout=30
    )
    stats.session_state["quiz"] = QuizScreen(
        files=RoundFiles(progress=tmp_path / "progress.db")
    )
    stats.run()
    assert not stats.exception
    assert "progress.db" in texts(stats)


def test_save_off_saves_nothing(tmp_path):
    at = page(tmp_path)
    at.checkbox(key="save").uncheck()
    at.button(key="start").click().run()
    answer(at, card("hm-telomeres-name").answers[0])
    assert not (tmp_path / "progress.db").exists()


def test_practise_deals_a_card_that_is_not_due(tmp_path):
    at = page(tmp_path)
    at.button(key="start").click().run()
    answer(at, card("hm-telomeres-name").answers[0])
    button(at, "Next →").click().run()
    at.button(key="new").click().run()
    at.checkbox(key="practise").check()
    at.button(key="start").click().run()
    assert "Question 1 of 1" in [s.value for s in at.subheader]
    assert "Practise" in [c.label for c in at.checkbox]


def test_settings_are_locked_while_a_quiz_runs(tmp_path):
    at = page(tmp_path)
    at.button(key="start").click().run()
    assert at.checkbox(key="save").disabled
    assert at.selectbox(key="topic").disabled


def test_stats_page_with_no_progress_creates_no_file(tmp_path):
    files = RoundFiles(progress=tmp_path / "progress.db")
    stats = AppTest.from_file(
        str(cli.WEB_PAGE.with_name("web_pages") / "stats.py"), default_timeout=30
    )
    stats.session_state["quiz"] = QuizScreen(files=files)
    stats.run()
    assert not stats.exception
    assert "all new" in texts(stats)
    assert not (tmp_path / "progress.db").exists()


# --- longevity web --------------------------------------------------------------------


def test_longevity_web_serves_the_page_from_the_project_folder(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "serve", lambda page, cwd: calls.append((page, cwd)) or 0)
    assert cli.main(["web"]) == 0
    assert calls == [(cli.WEB_PAGE, ROOT)]
    assert cli.WEB_PAGE.exists()


def test_streamlit_config_keeps_it_local():
    config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert 'address = "127.0.0.1"' in config
    assert "gatherUsageStats = false" in config
    assert 'toolbarMode = "minimal"' in config
    assert "headless = true" in config
