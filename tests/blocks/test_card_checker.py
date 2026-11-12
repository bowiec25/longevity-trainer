"""Tests for the card_checker block: contract (ID card + SPEC) and behaviour (from SPEC.md).

The real `claude` never runs: check_card gets a fake `ask`, run_exam a fake `check`.
"""

import importlib
import json
from pathlib import Path

import pytest

import longevity_trainer.blocks.card_checker as block
from longevity_trainer.blocks.card_bank import ROOT, LongevityCard
from quizkit.blocks.base import missing_spec_sections, spec_section
from quizkit.claude import ClaudeError, ClaudeReply

SPEC_MD = Path(block.__file__).parent / "SPEC.md"
GOALS_MD = ROOT / "docs" / "LEARNING_GOALS.md"
EXAM_FILE = ROOT / "tests" / "data" / "card_eval.jsonl"


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "card_checker"
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
        "card",
        "ask",
        "model",
        "cases_file",
        "show",
    }
    assert set(block.BLOCK_SPEC.outputs) == {
        "check_card",
        "CardVerdict",
        "RULES_TEXT",
        "PROMPT_VERSION",
        "ExamCase",
        "load_exam",
        "run_exam",
        "ExamReport",
        "MAX_FALSE_FLAG_SHARE",
        "MAX_RULES_NAMED",
    }


# ---- Behaviour (from SPEC.md) ----------------------------------------------------
# Called as block.check_card / block.RULES_TEXT / ... (not imported at the top), so
# the contract tests above still run before the block is built.


def make_card(card_id: str = "t-rapa-mice", **changes) -> LongevityCard:
    data = {
        "id": card_id,
        "kind": "fact",
        "topic": "rapamycin",
        "question": "What did rapamycin do to lifespan in late-life mice?",
        "answers": ["Extended it", "It made them live longer"],
        "receipt": {
            "source": "harrison-2009",
            "quote": "rapamycin fed late in life extends lifespan in genetically "
            "heterogeneous mice",
            "page": 3,
        },
    }
    return LongevityCard.model_validate({**data, **changes})


def reply(text: str) -> ClaudeReply:
    return ClaudeReply(
        text=text,
        model="claude-haiku-test",
        input_tokens=100,
        output_tokens=10,
        cost_usd=0.0,
    )


def fake_ask(payload=None, text=None, raises=None):
    """An `ask` that records each call and returns one fixed reply."""
    calls: list[dict] = []
    if payload is None:
        payload = {"ok": True, "rules": [], "reason": "The quote backs the answer."}

    def ask(prompt, model="haiku", system="", json_schema=None, **kwargs):
        calls.append(
            {
                "prompt": prompt,
                "model": model,
                "system": system,
                "json_schema": json_schema,
                **kwargs,
            }
        )
        if raises is not None:
            raise raises
        return reply(text if text is not None else json.dumps(payload))

    return ask, calls


# -- RULES_TEXT and PROMPT_VERSION -------------------------------------------------


def goals_section_2() -> tuple[str, str]:
    """(section 2 with its heading, without it), cut from the real file."""
    lines = GOALS_MD.read_text("utf-8").split("\n")
    start = next(i for i, ln in enumerate(lines) if ln.startswith("## 2."))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("## "))
    whole = "\n".join(lines[start:end]).strip()
    body = "\n".join(lines[start + 1 : end]).strip()
    return whole, body


def test_rules_text_is_section_2_word_for_word():
    whole, body = goals_section_2()
    assert body and body in block.RULES_TEXT
    assert block.RULES_TEXT.strip() in whole


def test_prompt_version_is_a_non_empty_string():
    assert isinstance(block.PROMPT_VERSION, str) and block.PROMPT_VERSION.strip()


def test_missing_section_2_raises_at_import(tmp_path, monkeypatch):
    """A checker without its rules must not run. (Assumes the path comes from ROOT.)"""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "LEARNING_GOALS.md").write_text(
        "# Learning goals\n\n## 1. What I want to learn\n\ntext\n\n## 3. Examples\n",
        "utf-8",
    )
    from longevity_trainer.blocks import card_bank

    try:
        with monkeypatch.context() as m:
            m.setattr(card_bank, "ROOT", tmp_path)
            with pytest.raises(RuntimeError):
                importlib.reload(block)
    finally:
        importlib.reload(block)  # put the real module back for later tests


# -- Prompt ------------------------------------------------------------------------


def test_system_prompt_contains_rules_text():
    ask, calls = fake_ask()
    block.check_card(make_card(), ask=ask)
    assert len(calls) == 1
    assert block.RULES_TEXT.strip() in calls[0]["system"]


def test_user_prompt_holds_the_card():
    card = make_card()
    ask, calls = fake_ask()
    block.check_card(card, ask=ask)
    prompt = calls[0]["prompt"]
    assert card.question in prompt
    for answer in card.answers:
        assert answer in prompt
    assert card.kind in prompt
    assert card.receipt.quote in prompt
    assert card.receipt.source in prompt


def test_reply_schema_is_passed():
    ask, calls = fake_ask()
    block.check_card(make_card(), ask=ask)
    schema = calls[0]["json_schema"]
    assert isinstance(schema, dict)
    assert {"ok", "rules", "reason"} <= set(schema.get("properties", {}))


@pytest.mark.parametrize("model", ["haiku", "sonnet"])
def test_chosen_model_is_passed(model):
    ask, calls = fake_ask()
    block.check_card(make_card(), ask=ask, model=model)
    assert calls[0]["model"] == model


def test_default_model_is_haiku():
    ask, calls = fake_ask()
    block.check_card(make_card(), ask=ask)
    assert calls[0]["model"] == "haiku"


# -- Verdicts ----------------------------------------------------------------------


def test_ok_reply_comes_back_as_verdict():
    ask, _ = fake_ask({"ok": True, "rules": [], "reason": "Backed word for word."})
    verdict = block.check_card(make_card(), ask=ask)
    assert isinstance(verdict, block.CardVerdict)
    assert (verdict.ok, verdict.rules, verdict.reason) == (
        True,
        [],
        "Backed word for word.",
    )


def test_fail_reply_comes_back_as_verdict():
    ask, _ = fake_ask({"ok": False, "rules": [2, 3], "reason": "Mice, not people."})
    verdict = block.check_card(make_card(), ask=ask)
    assert (verdict.ok, verdict.rules, verdict.reason) == (
        False,
        [2, 3],
        "Mice, not people.",
    )


def test_duplicate_rules_kept_once_in_order():
    ask, _ = fake_ask({"ok": False, "rules": [4, 2, 4, 2], "reason": "Trivia."})
    assert block.check_card(make_card(), ask=ask).rules == [4, 2]


BAD_REPLIES = {
    "not json": "this is not json",
    "not an object": json.dumps([1, 2]),
    "missing ok": json.dumps({"rules": [], "reason": "fine"}),
    "missing rules": json.dumps({"ok": True, "reason": "fine"}),
    "missing reason": json.dumps({"ok": True, "rules": []}),
    "rule 1": json.dumps({"ok": False, "rules": [1], "reason": "x"}),
    "rule 7": json.dumps({"ok": False, "rules": [7], "reason": "x"}),
    "ok with rules": json.dumps({"ok": True, "rules": [3], "reason": "x"}),
    "not ok with none": json.dumps({"ok": False, "rules": [], "reason": "x"}),
    "empty reason": json.dumps({"ok": True, "rules": [], "reason": ""}),
    "blank reason": json.dumps({"ok": True, "rules": [], "reason": "   "}),
}


@pytest.mark.parametrize("text", BAD_REPLIES.values(), ids=BAD_REPLIES.keys())
def test_invalid_reply_raises_claude_error(text):
    ask, _ = fake_ask(text=text)
    with pytest.raises(ClaudeError, match="bad reply"):
        block.check_card(make_card(), ask=ask)


def test_claude_error_from_ask_propagates():
    ask, calls = fake_ask(raises=ClaudeError("timed out"))
    with pytest.raises(ClaudeError, match="timed out"):
        block.check_card(make_card(), ask=ask)
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("ok", "rules"), [(True, [3]), (False, [])], ids=["ok-with-rules", "fail-no-rules"]
)
def test_card_verdict_rejects_inconsistent_shapes(ok, rules):
    with pytest.raises(ValueError):
        block.CardVerdict(ok=ok, rules=rules, reason="x")


def test_card_verdict_rejects_empty_reason():
    with pytest.raises(ValueError):
        block.CardVerdict(ok=True, rules=[], reason="")


# -- Exam scoring (fake check) -----------------------------------------------------


def case(case_id: str, expected: str, rules=()):
    return block.ExamCase(
        id=case_id,
        expected=expected,
        rules=list(rules),
        why="test",
        origin="test",
        card=make_card(case_id),
    )


def exam(n_good: int = 3, n_bad: int = 5):
    """Good cards g0.. and bad cards b0.. (each bad card's accepted rule is 3)."""
    good = [case(f"g{i}", "pass") for i in range(n_good)]
    bad = [case(f"b{i}", "fail", [3]) for i in range(n_bad)]
    return good + bad


def fake_check(answers: dict | None = None):
    """A `check` answering each card by id; default = the right answer, rule 3.

    answers[id] is "ok", a rule number (fail naming that rule), or an exception.
    """
    answers = answers or {}
    calls: list[str] = []

    def check(card, **kwargs):
        calls.append(card.id)
        answer = answers.get(card.id, "ok" if card.id.startswith("g") else 3)
        if isinstance(answer, Exception):
            raise answer
        if answer == "ok":
            return block.CardVerdict(ok=True, rules=[], reason=f"{card.id} looks fine")
        return block.CardVerdict(
            ok=False, rules=[answer], reason=f"{card.id} breaks {answer}"
        )

    check.calls = calls
    return check


def score(cases, answers=None):
    lines: list[str] = []
    check = fake_check(answers)
    report = block.run_exam(cases, check=check, show=lines.append)
    return report, "\n".join(lines), check


def test_all_right_passes():
    report, _, check = score(exam())
    assert isinstance(report, block.ExamReport)
    assert (report.total, report.bad_cards) == (8, 5)
    assert (report.caught, report.right_rule) == (5, 5)
    assert (report.false_flags, report.errors) == (0, 0)
    assert report.passed is True
    assert sorted(check.calls) == sorted(c.id for c in exam())  # each case once


def test_one_bad_card_missed_fails():
    report, _, _ = score(exam(), {"b0": "ok"})
    assert report.caught == 4
    assert report.passed is False


def test_caught_with_unlisted_rule_is_caught_not_right_rule():
    report, _, _ = score(exam(), {"b0": 5})
    assert report.caught == 5
    assert report.right_rule == 4


def test_two_wrong_rules_still_pass():
    report, _, _ = score(exam(), {"b0": 5, "b1": 6})
    assert report.right_rule == 3
    assert report.passed is True


def test_three_wrong_rules_fail():
    report, _, _ = score(exam(), {"b0": 5, "b1": 6, "b2": 2})
    assert report.right_rule == 2
    assert report.passed is False


def test_any_accepted_rule_counts_as_right():
    cases = exam(1, 1) + [case("b9", "fail", [2, 4])]
    report, _, _ = score(cases, {"b9": 4})
    assert report.right_rule == 2


def test_max_false_flag_share_is_one_third():
    assert block.MAX_FALSE_FLAG_SHARE == pytest.approx(1 / 3)


def test_max_rules_named_is_three():
    assert block.MAX_RULES_NAMED == 3


def flags(n: int) -> dict:
    return {f"g{i}": 4 for i in range(n)}


@pytest.mark.parametrize(
    "n_good, n_flags, passed",
    [(12, 4, True), (12, 5, False), (6, 2, True), (6, 3, False)],
)
def test_false_flags_up_to_a_third_of_good_cards_pass(n_good, n_flags, passed):
    report, _, _ = score(exam(n_good=n_good), flags(n_flags))
    assert report.false_flags == n_flags
    assert report.passed is passed


def test_one_error_fails_and_the_exam_goes_on():
    report, out, check = score(exam(), {"g2": ClaudeError("timed out")})
    assert report.errors == 1
    assert report.passed is False
    assert len(check.calls) == 8  # went on after the error
    assert "timed out" in out


def test_error_on_a_bad_card_is_not_a_catch():
    report, _, _ = score(exam(), {"b0": ClaudeError("timed out")})
    assert report.errors == 1
    assert report.caught == 4
    assert report.passed is False


def test_empty_exam_does_not_pass():
    report, _, check = score([])
    assert report.total == 0
    assert report.passed is False
    assert check.calls == []


def test_each_miss_prints_its_reason():
    _, out, _ = score(exam(), {"b0": "ok", "g0": 4, "b1": 6})
    assert "b0 looks fine" in out
    assert "g0 breaks 4" in out
    assert "b1 breaks 6" in out


def test_one_line_per_case_with_tick_or_cross():
    _, out, _ = score(exam(), {"b0": "ok"})
    lines = out.split("\n")
    for c in exam():
        assert any(c.id in ln for ln in lines)
    assert any("✗" in ln and "b0" in ln for ln in lines)
    assert any("✓" in ln and "g0" in ln for ln in lines)


def test_report_records_time_and_prompt_version():
    report, out, _ = score(exam())
    assert report.seconds >= 0
    assert isinstance(report.prompt_version, str)
    assert report.prompt_version in out


# -- load_exam ---------------------------------------------------------------------


def test_load_exam_reads_the_real_exam():
    cases = block.load_exam(EXAM_FILE)
    assert len(cases) == 29
    assert all(isinstance(c, block.ExamCase) for c in cases)
    assert all(isinstance(c.card, LongevityCard) for c in cases)
    assert {c.expected for c in cases} == {"pass", "fail"}


def test_load_exam_defaults_to_the_real_exam():
    assert len(block.load_exam()) == 29


def good_line(case_id="x1", **changes) -> dict:
    data = {
        "id": case_id,
        "expected": "pass",
        "rules": [],
        "why": "fine",
        "origin": "test",
        "card": json.loads(make_card(case_id).model_dump_json()),
    }
    return {**data, **changes}


BAD_LINES = {
    "invalid json": "{not json",
    "invalid card": json.dumps(good_line("x2", card={"id": "x2", "kind": "fact"})),
    "unknown expected": json.dumps(good_line("x2", expected="maybe")),
    "fail with no rules": json.dumps(good_line("x2", expected="fail", rules=[])),
    "pass with rules": json.dumps(good_line("x2", expected="pass", rules=[3])),
}


@pytest.mark.parametrize("bad", BAD_LINES.values(), ids=BAD_LINES.keys())
def test_bad_exam_line_names_its_line_number(tmp_path, bad):
    path = tmp_path / "exam.jsonl"
    path.write_text(json.dumps(good_line()) + "\n" + bad + "\n", "utf-8")
    with pytest.raises(ValueError, match=r"line 2\b"):
        block.load_exam(path)


# -- CLI ---------------------------------------------------------------------------


def real_report(passing: bool):
    """A genuine ExamReport from run_exam, passing or not."""
    report, _, _ = score(exam(), None if passing else {"b0": "ok"})
    assert report.passed is passing
    return report


@pytest.mark.parametrize(("passing", "code"), [(True, 0), (False, 1)])
def test_cli_exit_code_follows_the_report(monkeypatch, passing, code):
    from longevity_trainer.cli import main

    report = real_report(passing)
    seen: list = []

    def fake_run_exam(cases, check=None, **kwargs):
        seen.append(check)
        return report

    monkeypatch.setattr("longevity_trainer.cli.load_exam", lambda *a, **k: [])
    monkeypatch.setattr("longevity_trainer.cli.run_exam", fake_run_exam)
    assert main(["check-cards-exam", "--model", "haiku"]) == code
    assert len(seen) == 1 and callable(seen[0])


# -- Added SPEC lines: strict right_rule, load_exam ids/rules, reply types, CLI ----


def multi_rule_check(rules_by_id: dict):
    """A `check` failing each listed card with the given rule list; others ok."""

    def check(card, **kwargs):
        if card.id in rules_by_id:
            return block.CardVerdict(ok=False, rules=rules_by_id[card.id], reason="x")
        return block.CardVerdict(ok=True, rules=[], reason="fine")

    return check


def test_verdict_naming_extra_rules_is_caught_not_right_rule():
    cases = [case("b0", "fail", [3])]
    check = multi_rule_check({"b0": [2, 3, 4, 5, 6]})
    report = block.run_exam(cases, check=check, show=lambda s: None)
    assert (report.caught, report.right_rule) == (1, 0)


def test_verdict_within_allowed_rules_is_right_rule():
    cases = [case("b0", "fail", [3, 5])]
    check = multi_rule_check({"b0": [3]})
    report = block.run_exam(cases, check=check, show=lambda s: None)
    assert (report.caught, report.right_rule) == (1, 1)


@pytest.mark.parametrize("rule", [1, 7])
def test_load_exam_rejects_rule_outside_2_to_6(tmp_path, rule):
    path = tmp_path / "exam.jsonl"
    bad = good_line("x2", expected="fail", rules=[rule])
    path.write_text(json.dumps(good_line()) + "\n" + json.dumps(bad) + "\n", "utf-8")
    with pytest.raises(ValueError, match=r"line 2\b"):
        block.load_exam(path)


def test_load_exam_rejects_repeated_id(tmp_path):
    path = tmp_path / "exam.jsonl"
    line = json.dumps(good_line("x1"))
    path.write_text(line + "\n" + line + "\n", "utf-8")
    with pytest.raises(ValueError, match=r"line 2\b"):
        block.load_exam(path)


WRONG_TYPES = {
    "ok as string": {"ok": "false", "rules": [3], "reason": "x"},
    "rule as string": {"ok": False, "rules": ["3"], "reason": "x"},
    "rule as list": {"ok": False, "rules": [[3]], "reason": "x"},
}


@pytest.mark.parametrize("payload", WRONG_TYPES.values(), ids=WRONG_TYPES.keys())
def test_reply_with_wrong_json_types_raises_claude_error(payload):
    ask, _ = fake_ask(payload)
    with pytest.raises(ClaudeError):
        block.check_card(make_card(), ask=ask)


def test_other_exception_from_check_counts_as_error_and_exam_goes_on():
    report, out, check = score(exam(), {"g1": RuntimeError("boom")})
    assert report.errors == 1
    assert report.passed is False
    assert len(check.calls) == 8
    assert "boom" in out


def test_exam_report_dump_includes_passed():
    dumped = real_report(True).model_dump()
    assert dumped["passed"] is True


def test_cli_dry_run_calls_no_claude(monkeypatch):
    from longevity_trainer.cli import main

    def no_claude(*a, **k):
        raise AssertionError("dry run called Claude")

    monkeypatch.setattr("longevity_trainer.cli.ask_claude", no_claude)
    assert main(["check-cards-exam", "--dry-run"]) == 0


def test_cli_limit_passes_only_that_many_cases(monkeypatch):
    from longevity_trainer.cli import main

    seen: list = []

    def fake_run_exam(cases, **kwargs):
        seen.append(list(cases))
        return real_report(True)

    monkeypatch.setattr("longevity_trainer.cli.load_exam", lambda *a, **k: exam())
    monkeypatch.setattr("longevity_trainer.cli.run_exam", fake_run_exam)
    main(["check-cards-exam", "--limit", "2"])
    assert len(seen) == 1 and len(seen[0]) == 2


def test_cli_holdout_loads_the_holdout_file(monkeypatch):
    from longevity_trainer.cli import main

    loaded: list = []

    def fake_load_exam(*args, **kwargs):
        loaded.extend(list(args) + list(kwargs.values()))
        return exam()

    monkeypatch.setattr("longevity_trainer.cli.load_exam", fake_load_exam)
    monkeypatch.setattr(
        "longevity_trainer.cli.run_exam", lambda *a, **k: real_report(True)
    )
    main(["check-cards-exam", "--holdout"])
    assert block.HOLDOUT_FILE in loaded


def test_cli_bad_exam_line_prints_it_and_exits_1(monkeypatch, capsys):
    from longevity_trainer.cli import main

    def bad_load(*a, **k):
        raise ValueError("x line 3: bad")

    monkeypatch.setattr("longevity_trainer.cli.load_exam", bad_load)
    assert main(["check-cards-exam"]) == 1
    captured = capsys.readouterr()
    assert "x line 3: bad" in captured.out + captured.err


def test_verdict_with_an_allowed_rule_plus_another_is_right_rule():
    cases = [case("b0", "fail", [3])]
    check = multi_rule_check({"b0": [2, 3]})
    report = block.run_exam(cases, check=check, show=lambda s: None)
    assert (report.caught, report.right_rule) == (1, 1)


def test_verdict_naming_four_rules_is_caught_not_right_rule():
    cases = [case("b0", "fail", [3])]
    check = multi_rule_check({"b0": [2, 3, 4, 6]})
    report = block.run_exam(cases, check=check, show=lambda s: None)
    assert (report.caught, report.right_rule) == (1, 0)
