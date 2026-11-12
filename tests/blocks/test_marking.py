"""Tests for the marking block: contract (ID card + SPEC) and behaviour (from SPEC.md).

The real `claude` never runs: every judge gets a fake `ask` (tests/conftest.py).
"""

import json
import re
from pathlib import Path

import pytest

import longevity_trainer.blocks.marking as block
from quizkit.blocks.base import missing_spec_sections, spec_section
from quizkit.blocks.judge import WORD_RUBRIC
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
    }
    assert set(block.BLOCK_SPEC.outputs) == {
        "make_judge",
        "SUBJECT",
        "CONCEPT_RUBRIC",
        "Verdict",
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
