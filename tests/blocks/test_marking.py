"""Tests for the marking block: contract (ID card + SPEC) and behaviour (from SPEC.md).

The real `claude` never runs: every judge gets a fake `ask` (tests/conftest.py).
"""

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

import longevity_trainer.blocks.marking as block
from longevity_trainer import cli
from longevity_trainer.blocks.card_bank import load_cards
from quizkit.blocks.base import missing_spec_sections, spec_section
from quizkit.blocks.judge import WORD_RUBRIC
from quizkit.blocks.judge.eval import EvalReport
from quizkit.claude import ClaudeError, ClaudeReply
from quizkit.models import Question, Verdict

SPEC_MD = Path(block.__file__).parent / "SPEC.md"


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "marking"
    assert block.BLOCK_SPEC.kind == "agent"


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


def test_block_spec_lists_spec_inputs_and_outputs():
    assert set(block.BLOCK_SPEC.inputs) == {
        "question",
        "typed",
        "cache_file",
        "ask",
        "before_asking",
        "cases",
        "cards",
    }
    assert set(block.BLOCK_SPEC.outputs) == {
        "make_judge",
        "SUBJECT",
        "CONCEPT_RUBRIC",
        "Verdict",
        "MarkingCase",
        "MARKING_EVAL_FILE",
        "load_marking_cases",
        "check_card_ids",
        "run_marking_eval",
    }


# ---- Behaviour (from SPEC.md) ----------------------------------------------------
# Called as block.make_judge / block.SUBJECT / ... (not imported at the top), so the
# contract tests above still run before the block is built.


def question(mode: str, card_id: str = "hallmark-01") -> Question:
    return Question(
        card_id=card_id,
        mode=mode,
        shown={"question": "What happens to telomeres as cells divide?"},
        accepted_answers=["telomere attrition"],
    )


def fake_ask(correct=True, reason="Same idea in other words.", raises=None):
    """An `ask` that records each call and returns one fixed JSON reply."""
    calls: list[dict] = []

    def ask(prompt, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        if raises is not None:
            raise raises
        return ClaudeReply(
            text=json.dumps({"reason": reason, "correct": correct}),
            model="claude-haiku-test",
            input_tokens=100,
            output_tokens=10,
            cost_usd=0.0,
        )

    return ask, calls


def cache_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]


# -- Routing -----------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["name", "fact"])
def test_name_and_fact_use_word_rubric(mode):
    ask, calls = fake_ask()
    block.make_judge(ask=ask)(question(mode), "telomeres getting shorter")
    assert len(calls) == 1
    system = calls[0]["system"]
    assert WORD_RUBRIC.strip() in system
    assert block.CONCEPT_RUBRIC.strip() not in system


@pytest.mark.parametrize("mode", ["term", "explain"])
def test_term_and_explain_use_concept_rubric(mode):
    ask, calls = fake_ask()
    block.make_judge(ask=ask)(question(mode), "they get shorter each division")
    assert len(calls) == 1
    system = calls[0]["system"]
    assert block.CONCEPT_RUBRIC.strip() in system
    assert WORD_RUBRIC.strip() not in system


def test_ask_gets_a_json_schema():
    ask, calls = fake_ask()
    block.make_judge(ask=ask)(question("explain"), "they shorten")
    assert isinstance(calls[0].get("json_schema"), dict)


# -- Outputs: SUBJECT, CONCEPT_RUBRIC ----------------------------------------------


def test_subject_is_one_longevity_sentence():
    assert isinstance(block.SUBJECT, str) and block.SUBJECT.strip()
    assert "longevity" in block.SUBJECT.lower()


@pytest.mark.parametrize("mode", ["name", "fact", "term", "explain"])
def test_subject_is_in_every_prompt(mode):
    ask, calls = fake_ask()
    block.make_judge(ask=ask)(question(mode), "shorter")
    assert block.SUBJECT.strip() in calls[0]["prompt"]


def test_concept_rubric_covers_key_rules():
    rubric = block.CONCEPT_RUBRIC.lower()
    assert rubric.strip() and block.CONCEPT_RUBRIC.strip() != WORD_RUBRIC.strip()
    assert "accept" in rubric and "reject" in rubric
    assert "own words" in rubric
    assert "key idea" in rubric or "main point" in rubric
    assert "unsure" in rubric or "not sure" in rubric


def test_concept_rubric_rejects_partial_answers():
    """Reject: an answer covering only some of the parts asked for."""
    assert "parts" in block.CONCEPT_RUBRIC.lower()


def test_concept_rubric_rejects_moving_a_finding_across_species():
    """Reject: moving a finding to a different species or group (mice -> people)."""
    rubric = block.CONCEPT_RUBRIC.lower()
    assert "species" in rubric


def test_prompt_holds_question_and_model_answer():
    ask, calls = fake_ask()
    block.make_judge(ask=ask)(question("explain"), "they shorten")
    prompt = calls[0]["prompt"]
    assert "What happens to telomeres as cells divide?" in prompt
    assert "telomere attrition" in prompt
    assert "they shorten" in prompt


# -- Length limits -----------------------------------------------------------------


def test_150_char_explanation_is_sent():
    ask, calls = fake_ask()
    verdict = block.make_judge(ask=ask)(question("explain"), "a" * 150)
    assert len(calls) == 1
    assert verdict.source == "claude"


def test_150_char_name_answer_is_too_long():
    ask, calls = fake_ask()
    verdict = block.make_judge(ask=ask)(question("name"), "a" * 150)
    assert calls == []
    assert (verdict.correct, verdict.source) == (False, "not_checked")
    assert "too long" in verdict.reason


def test_400_char_explanation_is_sent():
    ask, calls = fake_ask()
    block.make_judge(ask=ask)(question("term"), "a" * 400)
    assert len(calls) == 1


def test_401_char_explanation_is_too_long():
    ask, calls = fake_ask()
    verdict = block.make_judge(ask=ask)(question("explain"), "a" * 401)
    assert calls == []
    assert (verdict.correct, verdict.source) == (False, "not_checked")
    assert "too long" in verdict.reason


@pytest.mark.parametrize("mode", ["name", "explain"])
def test_blank_answer_is_not_sent(mode):
    ask, calls = fake_ask()
    verdict = block.make_judge(ask=ask)(question(mode), "   ")
    assert calls == []
    assert (verdict.correct, verdict.source) == (False, "not_checked")


# -- Verdicts pass through ---------------------------------------------------------


@pytest.mark.parametrize("correct", [True, False])
@pytest.mark.parametrize("mode", ["name", "explain"])
def test_fake_verdict_and_reason_come_back(mode, correct):
    ask, _ = fake_ask(correct=correct, reason="Because of the mechanism.")
    verdict = block.make_judge(ask=ask)(question(mode), "shorter telomeres")
    assert isinstance(verdict, Verdict)
    assert verdict.correct is correct
    assert verdict.reason == "Because of the mechanism."
    assert verdict.source == "claude"


def test_verdict_is_quizkit_verdict():
    assert block.Verdict is Verdict


@pytest.mark.parametrize("mode", ["fact", "explain"])
def test_failing_ask_gives_not_checked(mode):
    ask, calls = fake_ask(raises=ClaudeError("timed out"))
    verdict = block.make_judge(ask=ask)(question(mode), "shorter")
    assert len(calls) == 1
    assert (verdict.correct, verdict.source) == (False, "not_checked")
    assert verdict.reason


def test_bad_reply_gives_not_checked():
    def ask(prompt, **kwargs):
        return ClaudeReply(
            text="not json", model="m", input_tokens=0, output_tokens=0, cost_usd=0.0
        )

    verdict = block.make_judge(ask=ask)(question("explain"), "shorter")
    assert (verdict.correct, verdict.source) == (False, "not_checked")


# -- Cache -------------------------------------------------------------------------


def test_same_answer_asks_claude_once(tmp_path):
    ask, calls = fake_ask()
    judge = block.make_judge(cache_file=tmp_path / "cache.jsonl", ask=ask)
    first = judge(question("explain"), "they shorten")
    second = judge(question("explain"), "they shorten")
    assert len(calls) == 1
    assert first.source == "claude"
    assert second.source == "cache"
    assert second.correct == first.correct


def test_cache_file_survives_a_new_judge(tmp_path):
    cache = tmp_path / "cache.jsonl"
    ask, calls = fake_ask()
    block.make_judge(cache_file=cache, ask=ask)(question("name"), "shorter telomeres")
    again = block.make_judge(cache_file=cache, ask=ask)
    verdict = again(question("name"), "shorter telomeres")
    assert len(calls) == 1
    assert verdict.source == "cache"


def test_both_routes_share_one_cache_file(tmp_path):
    cache = tmp_path / "cache.jsonl"
    ask, calls = fake_ask()
    judge = block.make_judge(cache_file=cache, ask=ask)
    judge(question("name", "c1"), "shorter telomeres")
    judge(question("explain", "c2"), "they get shorter each division")
    assert len(calls) == 2
    lines = cache_lines(cache)
    assert len(lines) == 2
    again = block.make_judge(cache_file=cache, ask=ask)
    assert again(question("name", "c1"), "shorter telomeres").source == "cache"
    explain = again(question("explain", "c2"), "they get shorter each division")
    assert explain.source == "cache"
    assert len(calls) == 2


def test_routes_never_mix_in_the_cache(tmp_path):
    """Same card and answer, word vs concept route: each asks Claude itself."""
    ask, calls = fake_ask()
    judge = block.make_judge(cache_file=tmp_path / "cache.jsonl", ask=ask)
    judge(question("fact"), "shorter telomeres")
    verdict = judge(question("term"), "shorter telomeres")
    assert len(calls) == 2
    assert verdict.source == "claude"


def test_no_cache_file_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ask, _ = fake_ask()
    block.make_judge(ask=ask)(question("explain"), "they shorten")
    assert list(tmp_path.iterdir()) == []


# -- Failure modes -----------------------------------------------------------------


@pytest.mark.parametrize("mode", ["char", "Explain", "word"])
def test_unknown_mode_raises_value_error_naming_it(mode):
    ask, calls = fake_ask()
    judge = block.make_judge(ask=ask)
    with pytest.raises(ValueError, match=re.escape(mode)):
        judge(question(mode), "shorter")
    assert calls == []


# -- before_asking -----------------------------------------------------------------


def counter():
    hits: list[None] = []
    return hits, lambda: hits.append(None)


@pytest.mark.parametrize("mode", ["name", "explain"])
def test_before_asking_called_once_before_a_real_call(mode):
    order: list[str] = []
    ask, _ = fake_ask()

    def recording_ask(prompt, **kwargs):
        order.append("ask")
        return ask(prompt, **kwargs)

    judge = block.make_judge(
        ask=recording_ask, before_asking=lambda: order.append("before")
    )
    judge(question(mode), "shorter telomeres")
    assert order == ["before", "ask"]


def test_before_asking_not_called_for_a_cached_verdict(tmp_path):
    hits, before = counter()
    ask, calls = fake_ask()
    judge = block.make_judge(
        cache_file=tmp_path / "cache.jsonl", ask=ask, before_asking=before
    )
    judge(question("explain"), "they shorten")
    verdict = judge(question("explain"), "they shorten")
    assert verdict.source == "cache"
    assert len(hits) == 1 and len(calls) == 1


@pytest.mark.parametrize(
    ("mode", "typed"),
    [("name", "   "), ("explain", ""), ("name", "a" * 150), ("explain", "a" * 401)],
)
def test_before_asking_not_called_for_blank_or_too_long(mode, typed):
    hits, before = counter()
    ask, calls = fake_ask()
    block.make_judge(ask=ask, before_asking=before)(question(mode), typed)
    assert calls == [] and hits == []


def test_before_asking_defaults_to_none():
    ask, calls = fake_ask()
    block.make_judge(ask=ask)(question("fact"), "shorter")
    assert len(calls) == 1


# -- One shared failure count ------------------------------------------------------


def scripted_ask(outcomes):
    """An `ask` that fails or succeeds per call, in order ("fail" / "ok")."""
    calls: list[dict] = []
    ok, _ = fake_ask()

    def ask(prompt, **kwargs):
        calls.append({"prompt": prompt, **kwargs})
        if outcomes[len(calls) - 1] == "fail":
            raise ClaudeError("timed out")
        return ok(prompt, **kwargs)

    return ask, calls


def test_two_failures_across_routes_switch_marking_off():
    ask, calls = scripted_ask(["fail", "fail", "ok", "ok"])
    hits, before = counter()
    judge = block.make_judge(ask=ask, before_asking=before)
    judge(question("name", "c1"), "shorter")
    judge(question("explain", "c2"), "they shorten")
    assert len(calls) == 2
    verdict = judge(question("fact", "c3"), "something else")
    assert len(calls) == 2
    assert (verdict.correct, verdict.source) == (False, "not_checked")
    later = judge(question("term", "c4"), "another answer")
    assert len(calls) == 2 and later.source == "not_checked"
    assert len(hits) == 2  # off = no real call, so no "asking Claude..."


def test_one_failure_does_not_switch_marking_off():
    ask, calls = scripted_ask(["fail", "ok"])
    judge = block.make_judge(ask=ask)
    judge(question("explain", "c1"), "they shorten")
    verdict = judge(question("name", "c2"), "shorter")
    assert len(calls) == 2 and verdict.source == "claude"


def test_a_success_resets_the_failure_count():
    ask, calls = scripted_ask(["fail", "ok", "fail", "ok"])
    judge = block.make_judge(ask=ask)
    judge(question("name", "c1"), "a1")
    judge(question("explain", "c2"), "a2")
    judge(question("fact", "c3"), "a3")
    verdict = judge(question("term", "c4"), "a4")
    assert len(calls) == 4
    assert verdict.source == "claude"


# -- Eval runner (fake judge, from SPEC "Eval runner") -----------------------------


def card(card_id: str, kind: str = "name", answers=("telomere attrition",)):
    from longevity_trainer.blocks.card_bank import LongevityCard

    return LongevityCard(
        id=card_id,
        kind=kind,
        topic="hallmarks",
        question=f"Question for {card_id}: what is it?",
        answers=list(answers),
        receipt={
            "source": "some-source",
            "quote": "telomeres shorten with each cell division",
            "page": 1,
        },
    )


def case(card_id: str, typed: str, expected: bool, why: str = "label"):
    return block.MarkingCase(card_id=card_id, typed=typed, expected=expected, why=why)


def recording_judge(verdict_for):
    """A judge that records (question, typed) and returns verdict_for(question, typed)."""
    calls: list[tuple[Question, str]] = []

    def judge(q: Question, typed: str) -> Verdict:
        calls.append((q, typed))
        return verdict_for(q, typed)

    return judge, calls


def agreeing(cases):
    """A judge that says exactly what each case's label says."""
    labels = {(c.card_id, c.typed): c.expected for c in cases}
    return recording_judge(
        lambda q, typed: Verdict(
            correct=labels[(q.card_id, typed)], reason="fake", source="claude"
        )
    )


def quiet(_line: str) -> None:
    pass


def test_marking_case_fields_and_frozen():
    c = case("c1", "shorter telomeres", True, "")
    assert (c.card_id, c.typed, c.expected, c.why) == (
        "c1",
        "shorter telomeres",
        True,
        "",
    )
    with pytest.raises(ValidationError):
        c.typed = "other"


def test_marking_case_rejects_extra_fields():
    with pytest.raises(ValueError):
        block.MarkingCase(card_id="c1", typed="x", expected=True, why="", extra=1)


def test_marking_case_rejects_blank_typed():
    with pytest.raises(ValueError):
        block.MarkingCase(card_id="c1", typed="  ", expected=True, why="")


def test_marking_eval_file_is_the_labelled_data():
    assert isinstance(block.MARKING_EVAL_FILE, Path)
    assert block.MARKING_EVAL_FILE.parts[-3:] == ("tests", "data", "marking_eval.jsonl")
    assert block.MARKING_EVAL_FILE.exists()


def test_judge_agreeing_with_every_label_passes():
    cards = [card("c1"), card("c2", "explain")]
    cases = [case("c1", "a", True), case("c1", "b", False), case("c2", "c", True)]
    judge, calls = agreeing(cases)
    report = block.run_marking_eval(cases, cards, judge, show=quiet)
    assert isinstance(report, EvalReport)
    assert (report.total, report.right, report.wrong_yes, report.wrong_no) == (
        3,
        3,
        0,
        0,
    )
    assert report.not_checked == 0
    assert report.passed is True
    assert len(calls) == 3


def test_one_wrong_yes_fails_even_at_95_percent():
    cards = [card("c1")]
    cases = [case("c1", f"answer {i}", True) for i in range(19)]
    cases.append(case("c1", "bad answer", False))
    judge, _ = recording_judge(
        lambda q, typed: Verdict(correct=True, reason="fake", source="claude")
    )
    report = block.run_marking_eval(cases, cards, judge, show=quiet)
    assert (report.total, report.right, report.wrong_yes) == (20, 19, 1)
    assert report.passed is False


def test_wrong_no_is_counted():
    cards = [card("c1")]
    cases = [case("c1", "good", True)]
    judge, _ = recording_judge(
        lambda q, typed: Verdict(correct=False, reason="fake", source="claude")
    )
    report = block.run_marking_eval(cases, cards, judge, show=quiet)
    assert (report.right, report.wrong_no, report.wrong_yes) == (0, 1, 0)


@pytest.mark.parametrize("expected", [True, False])
def test_not_checked_counts_as_not_right(expected):
    cards = [card("c1")]
    cases = [case("c1", "anything", expected)]
    judge, _ = recording_judge(
        lambda q, typed: Verdict(correct=False, reason="down", source="not_checked")
    )
    report = block.run_marking_eval(cases, cards, judge, show=quiet)
    assert report.not_checked == 1
    assert report.right == 0
    assert report.passed is False


def test_seconds_is_a_number():
    cases = [case("c1", "a", True)]
    judge, _ = agreeing(cases)
    report = block.run_marking_eval(cases, [card("c1")], judge, show=quiet)
    assert isinstance(report.seconds, float) and report.seconds >= 0


@pytest.mark.parametrize("kind", ["name", "fact", "term", "explain"])
def test_judge_gets_the_cards_own_question(kind):
    """Built as the quiz builds it: mode = the card's kind, its answers accepted."""
    c = card("c1", kind, answers=("loss of proteostasis", "proteostasis"))
    cases = [case("c1", "proteins misfold", True)]
    judge, calls = agreeing(cases)
    block.run_marking_eval(cases, [card("other"), c], judge, show=quiet)
    q, typed = calls[0]
    assert typed == "proteins misfold"
    assert q.card_id == "c1"
    assert q.mode == kind
    assert q.accepted_answers == ["loss of proteostasis", "proteostasis"]
    assert q.shown["question"] == c.question


def test_marking_routes_as_in_a_quiz():
    """With the real make_judge, an explain card goes to the concept rubric."""
    ask, calls = fake_ask()
    cases = [case("c1", "they get shorter", True)]
    block.run_marking_eval(
        cases, [card("c1", "explain")], block.make_judge(ask=ask), show=quiet
    )
    assert len(calls) == 1
    assert block.CONCEPT_RUBRIC.strip() in calls[0]["system"]


def test_show_lines_start_with_the_right_marker():
    cases = [
        case("c1", "right yes", True),
        case("c1", "wrong yes", False),
        case("c1", "wrong no", True),
        case("c1", "unchecked", True),
    ]
    verdicts = {
        "right yes": Verdict(correct=True, reason="r1", source="claude"),
        "wrong yes": Verdict(correct=True, reason="r2", source="claude"),
        "wrong no": Verdict(correct=False, reason="r3", source="claude"),
        "unchecked": Verdict(correct=False, reason="r4", source="not_checked"),
    }
    judge, _ = recording_judge(lambda q, typed: verdicts[typed])
    lines: list[str] = []
    block.run_marking_eval(cases, [card("c1")], judge, show=lines.append)
    assert len(lines) == 4
    assert lines[0].startswith("✓")
    assert lines[1].startswith("✗ WRONG YES")
    assert lines[2].startswith("✗ wrong no")
    assert lines[3].startswith("?")
    for line, c in zip(lines, cases, strict=True):
        assert "c1" in line and c.typed in line
        assert verdicts[c.typed].reason in line


def test_unknown_card_id_raises_before_judging():
    cases = [case("c1", "a", True), case("no-such-card", "b", True)]
    judge, calls = agreeing(cases)
    with pytest.raises(ValueError, match="no-such-card"):
        block.run_marking_eval(cases, [card("c1")], judge, show=quiet)
    assert calls == []


def test_no_cases_gives_total_zero_not_passed():
    judge, calls = recording_judge(lambda q, typed: None)
    report = block.run_marking_eval([], [card("c1")], judge, show=quiet)
    assert report.total == 0
    assert report.passed is False
    assert calls == []


# -- load_marking_cases ------------------------------------------------------------


def test_load_reads_the_real_file():
    cases = block.load_marking_cases()
    assert cases and all(isinstance(c, block.MarkingCase) for c in cases)
    ids = {c.id for c in load_cards()}
    assert {c.card_id for c in cases} <= ids
    assert all(c.why.strip() for c in cases)


def test_load_one_case_per_non_blank_line(tmp_path):
    path = tmp_path / "cases.jsonl"
    rows = [
        {"card_id": "c1", "typed": "a", "expected": True, "why": "x"},
        {"card_id": "c2", "typed": "b", "expected": False, "why": ""},
    ]
    text = json.dumps(rows[0]) + "\n\n   \n" + json.dumps(rows[1]) + "\n"
    path.write_text(text, "utf-8")
    cases = block.load_marking_cases(path)
    assert [(c.card_id, c.typed, c.expected) for c in cases] == [
        ("c1", "a", True),
        ("c2", "b", False),
    ]


@pytest.mark.parametrize(
    "bad",
    [
        "not json",
        json.dumps({"card_id": "c2", "typed": "b"}),  # no expected
        json.dumps({"card_id": "c2", "typed": " ", "expected": True, "why": ""}),
        json.dumps({"card_id": "c2", "typed": "b", "expected": True, "x": 1}),
    ],
)
def test_load_bad_line_names_its_number(tmp_path, bad):
    path = tmp_path / "cases.jsonl"
    good = json.dumps({"card_id": "c1", "typed": "a", "expected": True, "why": ""})
    path.write_text(f"{good}\n{good}\n{bad}\n", "utf-8")
    with pytest.raises(ValueError, match=r"\b3\b"):
        block.load_marking_cases(path)


# -- CLI: longevity check-marking-eval ----------------------------------------------


def eval_report(passed: bool) -> EvalReport:
    return EvalReport(
        total=10,
        right=10 if passed else 8,
        wrong_yes=0 if passed else 1,
        wrong_no=0 if passed else 1,
        not_checked=0,
        seconds=0.1,
    )


def no_claude(*args, **kwargs):
    raise AssertionError("must not be called in a dry run")


def test_cli_dry_run_lists_cases_and_calls_nothing(monkeypatch, capsys):
    monkeypatch.setattr(cli, "make_judge", no_claude)
    monkeypatch.setattr(cli, "run_marking_eval", no_claude)
    monkeypatch.setattr(cli, "ask_claude", no_claude)
    assert cli.main(["check-marking-eval", "--dry-run"]) == 0
    out = capsys.readouterr().out
    for c in block.load_marking_cases():
        assert c.card_id in out


def test_cli_dry_run_limit_lists_only_first_n(monkeypatch, capsys):
    monkeypatch.setattr(cli, "make_judge", no_claude)
    monkeypatch.setattr(cli, "run_marking_eval", no_claude)
    assert cli.main(["check-marking-eval", "--dry-run", "--limit", "1"]) == 0
    out = capsys.readouterr().out
    cases = block.load_marking_cases()
    assert cases[0].typed in out
    assert cases[-1].typed not in out


@pytest.mark.parametrize(("passed", "code"), [(True, 0), (False, 1)])
def test_cli_exit_code_follows_the_report(monkeypatch, passed, code):
    seen: list[list] = []

    def fake_run(cases, cards, judge, *args, **kwargs):
        seen.append(list(cases))
        return eval_report(passed)

    monkeypatch.setattr(cli, "make_judge", lambda *a, **k: lambda q, typed: None)
    monkeypatch.setattr(cli, "run_marking_eval", fake_run)
    assert cli.main(["check-marking-eval"]) == code
    assert seen == [block.load_marking_cases()]


def test_cli_limit_passes_first_n_cases(monkeypatch):
    seen: list[list] = []

    def fake_run(cases, cards, judge, *args, **kwargs):
        seen.append(list(cases))
        return eval_report(True)

    monkeypatch.setattr(cli, "make_judge", lambda *a, **k: lambda q, typed: None)
    monkeypatch.setattr(cli, "run_marking_eval", fake_run)
    assert cli.main(["check-marking-eval", "--limit", "2"]) == 0
    assert seen == [block.load_marking_cases()[:2]]


# -- Eval runner: marks exactly as the quiz does (answer list first) ---------------

REAL_NAME_CARD = "hm-telomeres-name"  # a real bank card; answers include this one:
REAL_NAME_ANSWER = "telomere attrition"


def real_card():
    (c,) = [c for c in load_cards() if c.id == REAL_NAME_CARD]
    assert REAL_NAME_ANSWER in c.answers  # guard: the test relies on this answer
    return c


def never_called(q, typed):
    raise AssertionError("the judge must not be asked when the answer list says yes")


def test_judge_gets_exactly_the_cards_to_question():
    c = real_card()
    cases = [case(c.id, "chromosome ends wear down", True)]
    judge, calls = agreeing(cases)
    block.run_marking_eval(cases, load_cards(), judge, show=quiet)
    assert len(calls) == 1
    assert calls[0] == (c.to_question(), "chromosome ends wear down")


def test_answer_list_yes_is_not_sent_to_the_judge_and_counts_as_yes():
    c = real_card()
    cases = [case(c.id, REAL_NAME_ANSWER, True)]
    report = block.run_marking_eval(cases, [c], never_called, show=quiet)
    assert (report.total, report.right, report.not_checked) == (1, 1, 0)
    assert report.passed is True


def test_answer_list_yes_on_a_case_labelled_wrong_is_a_wrong_yes():
    c = real_card()
    cases = [case(c.id, REAL_NAME_ANSWER, False)]
    lines: list[str] = []
    report = block.run_marking_eval(cases, [c], never_called, show=lines.append)
    assert (report.right, report.wrong_yes) == (0, 1)
    assert report.passed is False
    assert lines[0].startswith("✗ WRONG YES")
    assert "answer list" in lines[0]  # the reason: accepted by the answer list


def test_a_one_letter_typo_of_a_long_answer_is_accepted_by_the_answer_list():
    c = real_card()
    typo = "telomere atrition"  # one letter missing from "telomere attrition"
    cases = [case(c.id, typo, True)]
    lines: list[str] = []
    report = block.run_marking_eval(cases, [c], never_called, show=lines.append)
    assert report.right == 1
    assert lines[0].startswith("✓")


def test_answer_list_yes_line_has_card_id_and_typed():
    c = real_card()
    lines: list[str] = []
    block.run_marking_eval(
        [case(c.id, REAL_NAME_ANSWER, True)], [c], never_called, show=lines.append
    )
    assert len(lines) == 1
    assert c.id in lines[0] and REAL_NAME_ANSWER in lines[0]


def test_judge_only_asked_for_what_the_answer_list_rejects():
    c = real_card()
    cases = [
        case(c.id, REAL_NAME_ANSWER, True),
        case(c.id, "ends of chromosomes fray", True),
    ]
    judge, calls = agreeing(cases)
    report = block.run_marking_eval(cases, [c], judge, show=quiet)
    assert [typed for _, typed in calls] == ["ends of chromosomes fray"]
    assert report.right == 2


# -- check_card_ids -----------------------------------------------------------------


def test_check_card_ids_passes_when_every_id_is_in_the_bank():
    cases = [case("c1", "a", True), case("c2", "b", False), case("c1", "c", True)]
    assert block.check_card_ids(cases, [card("c1"), card("c2")]) is None


def test_check_card_ids_names_every_unknown_id_in_case_order():
    cases = [
        case("zz-missing", "a", True),
        case("c1", "b", True),
        case("aa-missing", "c", True),
    ]
    with pytest.raises(ValueError) as err:
        block.check_card_ids(cases, [card("c1")])
    msg = str(err.value)
    assert "zz-missing" in msg and "aa-missing" in msg
    assert msg.index("zz-missing") < msg.index("aa-missing")
    assert "c1" not in msg.replace("zz-missing", "").replace("aa-missing", "")


def test_check_card_ids_with_no_cases_is_fine():
    assert block.check_card_ids([], [card("c1")]) is None


# -- load_marking_cases (via quizkit's load_jsonl_file) -----------------------------

GOOD_ROW = {"card_id": "c1", "typed": "a", "expected": True, "why": "x"}


def test_real_file_has_at_least_20_labelled_cases():
    cases = block.load_marking_cases()
    assert len(cases) >= 20
    assert all(c.why.strip() for c in cases)
    block.check_card_ids(cases, load_cards())  # every card_id is in the bank


def test_load_allows_many_cases_for_one_card(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_text(json.dumps(GOOD_ROW) + "\n" + json.dumps(GOOD_ROW) + "\n", "utf-8")
    assert len(block.load_marking_cases(path)) == 2


@pytest.mark.parametrize(
    ("bad", "field"),
    [
        (json.dumps({"card_id": "c2", "typed": "b", "why": ""}), "expected"),
        (json.dumps({**GOOD_ROW, "typed": "  "}), "typed"),
        (json.dumps({**GOOD_ROW, "colour": "red"}), "colour"),
    ],
)
def test_load_bad_line_names_its_number_and_the_bad_field(tmp_path, bad, field):
    path = tmp_path / "cases.jsonl"
    path.write_text(f"{json.dumps(GOOD_ROW)}\n\n{bad}\n", "utf-8")
    with pytest.raises(ValueError) as err:
        block.load_marking_cases(path)
    msg = str(err.value)
    assert re.search(r"\b3\b", msg)
    assert field in msg


def test_load_bom_and_crlf_are_fine(tmp_path):
    path = tmp_path / "cases.jsonl"
    row = json.dumps(GOOD_ROW).encode()
    path.write_bytes("﻿".encode() + row + b"\r\n" + row + b"\r\n")
    cases = block.load_marking_cases(path)
    assert [c.card_id for c in cases] == ["c1", "c1"]


@pytest.mark.parametrize("text", ["", "\n  \n\n"])
def test_load_blank_file_says_no_marking_eval_cases(tmp_path, text):
    path = tmp_path / "cases.jsonl"
    path.write_text(text, "utf-8")
    with pytest.raises(ValueError, match="no marking eval cases"):
        block.load_marking_cases(path)


def test_load_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        block.load_marking_cases(tmp_path / "nope.jsonl")


def test_load_non_utf8_file_raises_value_error(tmp_path):
    path = tmp_path / "cases.jsonl"
    path.write_bytes(b'{"card_id": "\xff", "typed": "a", "expected": true}\n')
    with pytest.raises(ValueError) as err:
        block.load_marking_cases(path)
    assert not isinstance(err.value, UnicodeDecodeError)


# -- CLI error paths: printed in full, exit 1, no traceback -------------------------


def fake_judge_maker(*args, **kwargs):
    return lambda q, typed: Verdict(correct=False, reason="fake", source="claude")


def use_eval_file(monkeypatch, path: Path) -> None:
    monkeypatch.setattr(
        cli, "load_marking_cases", lambda: block.load_marking_cases(path)
    )


def run_cli(capsys, *args) -> tuple[int, str]:
    code = cli.main(["check-marking-eval", *args])
    captured = capsys.readouterr()
    return code, captured.out + captured.err


DRY = [[], ["--dry-run"]]


@pytest.mark.parametrize("args", DRY)
def test_cli_missing_eval_file_exits_1_without_traceback(
    monkeypatch, capsys, tmp_path, args
):
    monkeypatch.setattr(cli, "make_judge", fake_judge_maker)
    use_eval_file(monkeypatch, tmp_path / "nope.jsonl")
    code, out = run_cli(capsys, *args)
    assert code == 1
    assert "nope.jsonl" in out
    assert "Traceback" not in out


@pytest.mark.parametrize("args", DRY)
def test_cli_empty_eval_file_exits_1_with_the_reason(
    monkeypatch, capsys, tmp_path, args
):
    monkeypatch.setattr(cli, "make_judge", fake_judge_maker)
    path = tmp_path / "cases.jsonl"
    path.write_text("\n\n", "utf-8")
    use_eval_file(monkeypatch, path)
    code, out = run_cli(capsys, *args)
    assert code == 1
    assert "no marking eval cases" in out
    assert "Traceback" not in out


@pytest.mark.parametrize("args", DRY)
def test_cli_bad_line_prints_the_bad_fields_name(monkeypatch, capsys, tmp_path, args):
    """The reason is printed in full, not just its first line."""
    monkeypatch.setattr(cli, "make_judge", fake_judge_maker)
    path = tmp_path / "cases.jsonl"
    bad = json.dumps({"card_id": "c2", "typed": "b", "why": ""})  # no "expected"
    path.write_text(f"{json.dumps(GOOD_ROW)}\n{bad}\n", "utf-8")
    use_eval_file(monkeypatch, path)
    code, out = run_cli(capsys, *args)
    assert code == 1
    assert "line 2" in out
    assert "expected" in out
    assert "Traceback" not in out


@pytest.mark.parametrize("args", DRY)
def test_cli_prints_a_multi_line_reason_in_full(monkeypatch, capsys, args):
    def boom():
        raise ValueError("cases.jsonl line 4: first part\nsecond part of the reason")

    monkeypatch.setattr(cli, "make_judge", fake_judge_maker)
    monkeypatch.setattr(cli, "load_marking_cases", boom)
    code, out = run_cli(capsys, *args)
    assert code == 1
    assert "first part" in out and "second part of the reason" in out


@pytest.mark.parametrize("args", DRY)
def test_cli_unknown_card_id_exits_1_naming_it(monkeypatch, capsys, args):
    monkeypatch.setattr(cli, "make_judge", fake_judge_maker)
    monkeypatch.setattr(
        cli,
        "load_marking_cases",
        lambda: [case(REAL_NAME_CARD, "x", True), case("no-such-card", "y", True)],
    )
    code, out = run_cli(capsys, *args)
    assert code == 1
    assert "no-such-card" in out
    assert "Traceback" not in out


@pytest.mark.parametrize("args", DRY)
def test_cli_bad_card_file_exits_1_with_the_full_reason(monkeypatch, capsys, args):
    def bad_bank(*a, **k):
        raise ValueError("hallmarks.jsonl line 3: 1 validation error\nkind\n  bad kind")

    monkeypatch.setattr(cli, "make_judge", fake_judge_maker)
    monkeypatch.setattr(cli, "load_cards", bad_bank)
    code, out = run_cli(capsys, *args)
    assert code == 1
    assert "hallmarks.jsonl line 3" in out and "bad kind" in out
    assert "Traceback" not in out


def test_cli_dry_run_with_known_card_ids_still_exits_0(monkeypatch, capsys):
    monkeypatch.setattr(cli, "make_judge", no_claude)
    monkeypatch.setattr(cli, "run_marking_eval", no_claude)
    monkeypatch.setattr(
        cli, "load_marking_cases", lambda: [case(REAL_NAME_CARD, "x", True)]
    )
    code, out = run_cli(capsys, "--dry-run")
    assert code == 0
    assert REAL_NAME_CARD in out


def test_cli_says_claude_didnt_answer_when_a_case_was_not_checked(monkeypatch, capsys):
    report = EvalReport(
        total=10, right=8, wrong_yes=0, wrong_no=0, not_checked=2, seconds=0.1
    )
    monkeypatch.setattr(cli, "make_judge", fake_judge_maker)
    monkeypatch.setattr(cli, "run_marking_eval", lambda *a, **k: report)
    code, out = run_cli(capsys)
    assert code == 1
    assert "didn't answer" in out.lower() or "did not answer" in out.lower()


def test_cli_no_didnt_answer_line_when_every_case_was_checked(monkeypatch, capsys):
    monkeypatch.setattr(cli, "make_judge", fake_judge_maker)
    monkeypatch.setattr(cli, "run_marking_eval", lambda *a, **k: eval_report(True))
    code, out = run_cli(capsys)
    assert code == 0
    assert "didn't answer" not in out.lower() and "did not answer" not in out.lower()


def test_cli_real_run_prints_the_model_and_the_prompt_version(monkeypatch, capsys):
    from quizkit.blocks.judge import PROMPT_VERSION

    fake_reply = ClaudeReply(
        text="{}",
        model="claude-haiku-x",
        input_tokens=100,
        output_tokens=10,
        cost_usd=0.001,
    )
    monkeypatch.setattr(cli, "_counting_ask", lambda: (no_claude, [fake_reply]))
    monkeypatch.setattr(cli, "make_judge", fake_judge_maker)
    monkeypatch.setattr(cli, "run_marking_eval", lambda *a, **k: eval_report(True))
    code, out = run_cli(capsys)
    assert code == 0
    assert "claude-haiku-x" in out
    assert re.search(
        rf"prompt[^\n]*(?<!\d){re.escape(PROMPT_VERSION)}(?!\d)", out, re.IGNORECASE
    ), out
