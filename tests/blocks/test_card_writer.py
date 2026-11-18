"""Tests for the card_writer block: contract (ID card + SPEC) and behaviour (from SPEC.md).

Test-first, black-box: the real Claude never runs (a fake `ask`), the card checker
is a fake `check`, and sources are tiny html/PDF files pinned in a temp folder.
"""

import hashlib
import json
import re
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import longevity_trainer.blocks.card_writer as block
from longevity_trainer.blocks.card_bank import ROOT, LongevityCard, load_cards
from longevity_trainer.blocks.card_checker import CardVerdict
from quizkit.blocks.base import missing_spec_sections, spec_section
from quizkit.claude import ClaudeError, ClaudeReply
from quizkit.download import DownloadError

SPEC_MD = Path(block.__file__).parent / "SPEC.md"
GOALS_MD = ROOT / "docs" / "LEARNING_GOALS.md"


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "card_writer"
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
        "topic",
        "source_id",
        "n",
        "ask",
        "model",
        "check",
        "taken_ids",
        "taken_questions",
        "sources_dir",
        "root",
        "fetch",
        "pages",
        "primer_text",
        "only_asks",
        "topics",
    }
    assert set(block.BLOCK_SPEC.outputs) == {
        "write_cards",
        "Draft",
        "Drop",
        "WriterReport",
        "PROMPT_VERSION",
        "slug",
        "ASKS",
        "REQUIRED_ASKS",
        "TOPICS_FILE",
        "load_topics",
    }


@pytest.fixture(autouse=True)
def no_real_primer(monkeypatch):
    """Safety net: the CLI never reads the real primer PDF or tags with real Claude.
    By default the primer can't be read (so a run prints its `not tagged` line);
    tests that need a primer or tagging patch `cli.load_primer` / `cli.tag_cards`."""
    from longevity_trainer import cli as cli_module

    def no_primer(*_a, **_k):
        raise FileNotFoundError("no primer in tests")

    def refuse(*_a, **_k):
        pytest.fail("a test tried to tag with the real primer_check (patch tag_cards)")

    monkeypatch.setattr(cli_module, "load_primer", no_primer)
    monkeypatch.setattr(cli_module, "tag_cards", refuse)


# ---- Behaviour (from SPEC.md) ----------------------------------------------------
# Called as block.write_cards / block.slug / ... (not imported at the top), so the
# contract tests above still run before the block is built.

S_WHAT = "Rapamycin is a drug that inhibits the protein kinase called mTOR."
S_HOW = "Rapamycin works by blocking mTORC1 signalling, which slows cell growth."
S_SURE = "In mice rapamycin extended lifespan, but evidence in humans is limited."
S_CATCH = "Rapamycin can suppress the immune system and cause mouth ulcers."
S_EXTRA = "Autophagy is the recycling of worn out parts inside the cell."
SENTENCES = [S_WHAT, S_HOW, S_SURE, S_CATCH, S_EXTRA]

TITLE = "Rapamycin review"
SOURCE_ID = "rapa-review"


def html_doc(sentences=SENTENCES) -> bytes:
    body = "".join(f"<p>{s}</p>" for s in sentences)
    return f"<html><body><h1>{TITLE}</h1>{body}</body></html>".encode()


def pin_source(
    sources_dir: Path, data: bytes, fmt: str = "html", sid: str = SOURCE_ID
) -> str:
    """Write <sid>.json pinning `data` (size + SHA-256); return its URL."""
    sources_dir.mkdir(exist_ok=True)
    url = f"https://example.org/{sid}.{fmt}"
    record = {
        "id": sid,
        "title": TITLE,
        "url": url,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "local_path": f"docs/{sid}.{fmt}",
        "format": fmt,
    }
    (sources_dir / f"{sid}.json").write_text(json.dumps(record), encoding="utf-8")
    return url


def draft(asks="what", question=None, answers=None, quote=S_WHAT, kind="fact"):
    return {
        "asks": asks,
        "kind": kind,
        "question": question or f"Question about rapamycin, asking {asks}?",
        "answers": answers or ["An answer"],
        "quote": quote,
    }


def good_drafts() -> list[dict]:
    return [
        draft("what", "What does rapamycin inhibit in the cell?", quote=S_WHAT),
        draft("how", "How does rapamycin slow cell growth?", quote=S_HOW),
        draft("how_sure", "How strong is the lifespan evidence?", quote=S_SURE),
        draft("catch", "What side effect can rapamycin cause?", quote=S_CATCH),
    ]


def reply(text: str) -> ClaudeReply:
    return ClaudeReply(
        text=text,
        model="claude-sonnet-test",
        input_tokens=0,
        output_tokens=0,
        cost_usd=0,
    )


def fake_ask(cards=None, text=None, raises=None):
    """An `ask` that records each call and returns {"cards": cards}."""
    calls: list[dict] = []

    def ask(prompt, model="sonnet", system="", json_schema=None, **kwargs):
        calls.append(
            {
                "prompt": prompt,
                "model": model,
                "system": system,
                "json_schema": json_schema,
            }
        )
        if raises is not None:
            raise raises
        return reply(text if text is not None else json.dumps({"cards": cards or []}))

    return ask, calls


def fake_check(answers: dict | None = None):
    """A `check` keyed by a word in the question: "ok" (default), a rule, or an error."""
    answers = answers or {}
    calls: list[LongevityCard] = []

    def check(card, **kwargs):
        calls.append(card)
        answer = next((v for k, v in answers.items() if k in card.question), "ok")
        if isinstance(answer, Exception):
            raise answer
        if answer == "ok":
            return CardVerdict(ok=True, rules=[], reason="fine")
        return CardVerdict(ok=False, rules=[answer], reason=f"breaks rule {answer}")

    check.calls = calls
    return check


@pytest.fixture
def env(tmp_path):
    """A pinned html source; `run(drafts, ...)` calls write_cards with fakes."""
    sources_dir = tmp_path / "sources"
    data = html_doc()
    url = pin_source(sources_dir, data)

    def fetch(u):
        assert u == url
        return data

    def run(drafts=None, topic="rapamycin", check=None, ask=None, **kwargs):
        if ask is None:
            ask, calls = fake_ask(good_drafts() if drafts is None else drafts)
        else:
            calls = None
        result = block.write_cards(
            topic,
            kwargs.pop("source_id", SOURCE_ID),
            ask=ask,
            check=check or fake_check(),
            sources_dir=sources_dir,
            root=tmp_path,
            fetch=fetch,
            **{"topics": TOPICS, **kwargs},  # not the real topics file
        )
        return result, calls

    run.sources_dir = sources_dir
    run.fetch = fetch
    run.root = tmp_path
    return run


# -- slug ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [("Epigenetic clocks!", "epigenetic-clocks"), ("  mTOR  ", "mtor")],
)
def test_slug(text, expected):
    assert block.slug(text) == expected


def test_prompt_version_is_a_non_empty_string():
    assert isinstance(block.PROMPT_VERSION, str) and block.PROMPT_VERSION.strip()


# -- Prompt --------------------------------------------------------------------------


def test_one_claude_call_per_run(env):
    _, calls = env()
    assert len(calls) == 1


def test_system_prompt_contains_all_of_learning_goals(env):
    _, calls = env()
    assert GOALS_MD.read_text("utf-8").strip() in calls[0]["system"]


def test_user_prompt_holds_topic_title_and_source_text(env):
    _, calls = env(topic="rapamycin")
    prompt = calls[0]["prompt"]
    assert "rapamycin" in prompt
    assert TITLE in prompt
    for sentence in SENTENCES:
        assert sentence in prompt


def test_n_is_in_the_prompt(env):
    _, calls = env(n=17)
    goals = GOALS_MD.read_text("utf-8").strip()
    assert "17" in calls[0]["system"].replace(goals, "") + calls[0]["prompt"]


def test_reply_schema_is_passed(env):
    _, calls = env()
    schema = calls[0]["json_schema"]
    assert isinstance(schema, dict)
    assert "cards" in schema.get("properties", {})


def test_default_model_is_sonnet(env):
    _, calls = env()
    assert calls[0]["model"] == "sonnet"


def test_chosen_model_is_passed_and_reported(env):
    result, calls = env(model="opus")
    assert calls[0]["model"] == "opus"
    assert result.report.model == "opus"


# -- Gates ---------------------------------------------------------------------------


def gates(result) -> list[str]:
    return [d.gate for d in result.drops]


def test_short_question_dropped_at_shape(env):
    result, _ = env([*good_drafts(), draft("what", question="Why??")])
    assert gates(result) == ["shape"]
    assert result.drops[0].question == "Why??"
    assert result.report.dropped_shape == 1


def test_blank_answer_dropped_at_shape(env):
    result, _ = env([*good_drafts(), draft("what", "What is mTOR in short?", ["  "])])
    assert gates(result) == ["shape"]


def test_quote_not_in_source_dropped_at_quote(env):
    fake = "Rapamycin doubled the lifespan of every human volunteer tested."
    result, _ = env(
        [*good_drafts(), draft("what", "What did it do in people?", quote=fake)]
    )
    assert gates(result) == ["quote"]
    assert result.report.dropped_quote == 1


def test_same_question_twice_second_is_repeat(env):
    first = draft("what", "What does rapamycin inhibit?", quote=S_WHAT)
    again = draft("what", "  what DOES   rapamycin inhibit? ", quote=S_WHAT)
    result, _ = env([first, *good_drafts()[1:], again])
    assert gates(result) == ["repeat"]
    assert result.drops[0].question.strip().lower().startswith("what does")
    assert result.report.dropped_repeat == 1
    assert len(result.kept) == 4


def test_checker_fail_dropped_with_its_reason(env):
    check = fake_check({"side effect": 4})
    result, _ = env(check=check)
    assert gates(result) == ["checker"]
    assert "breaks rule 4" in result.drops[0].reason
    assert result.report.dropped_checker == 1


def test_checker_error_drops_card_and_run_goes_on(env):
    check = fake_check({"slow cell growth": ClaudeError("timed out")})
    result, _ = env(check=check)
    assert gates(result) == ["checker"]
    assert result.drops[0].reason.startswith("checker error")
    assert result.report.checker_errors == 1
    assert len(check.calls) == 4  # went on after the error
    assert len(result.kept) == 3


def test_checker_sees_each_card_that_passed_earlier_gates(env):
    check = fake_check()
    env(check=check)
    assert [c.question for c in check.calls] == [d["question"] for d in good_drafts()]


def test_drops_listed_in_draft_order(env):
    fake = "Rapamycin doubled the lifespan of every human volunteer tested."
    drafts = [
        draft("what", "What breaks the checker here?", quote=S_WHAT),
        draft("what", "What is fake about this one?", quote=fake),
        draft("what", question="Short"),
        *good_drafts(),
        draft("how", "HOW does rapamycin slow  cell growth?", quote=S_HOW),
    ]
    result, _ = env(drafts, check=fake_check({"breaks the checker": 3}))
    assert gates(result) == ["checker", "quote", "shape", "repeat"]


def test_kept_cards_in_draft_order(env):
    result, _ = env()
    assert [c.question for c in result.kept] == [d["question"] for d in good_drafts()]
    assert all(isinstance(c, LongevityCard) for c in result.kept)


# -- Cards ---------------------------------------------------------------------------


def test_ids_follow_slug_asks_k(env):
    drafts = [
        draft("what", "What does rapamycin inhibit in the cell?", quote=S_WHAT),
        draft("how_sure", "How strong is the lifespan evidence?", quote=S_SURE),
        draft("what", "What kind of molecule is rapamycin?", quote=S_WHAT),
        draft("how", "How does rapamycin slow cell growth?", quote=S_HOW),
    ]
    result, _ = env(drafts)
    assert [c.id for c in result.kept] == [
        "rapamycin-what-1",
        "rapamycin-how-sure-1",
        "rapamycin-what-2",
        "rapamycin-how-1",
    ]


def test_ids_skip_taken_ids(env):
    drafts = [
        draft("what", "What does rapamycin inhibit in the cell?", quote=S_WHAT),
        draft("what", "What kind of molecule is rapamycin?", quote=S_WHAT),
    ]
    taken = {"rapamycin-what-1", "rapamycin-what-3"}
    result, _ = env(drafts, taken_ids=taken)
    assert [c.id for c in result.kept] == ["rapamycin-what-2", "rapamycin-what-4"]


def test_ids_never_repeat_within_a_run(env):
    drafts = [
        draft("what", f"What is rapamycin, take number {i}?", quote=S_WHAT)
        for i in range(5)
    ]
    result, _ = env(drafts)
    ids = [c.id for c in result.kept]
    assert len(ids) == len(set(ids)) == 5


def test_id_and_topic_use_slug_and_given_topic(env):
    result, _ = env(topic="Epigenetic clocks!")
    assert result.kept[0].id == "epigenetic-clocks-what-1"
    assert all(c.topic == "Epigenetic clocks!" for c in result.kept)


def test_card_kind_and_answers_come_from_the_draft(env):
    d = draft("what", "Name the kinase rapamycin inhibits.", ["mTOR"], S_WHAT, "name")
    result, _ = env([d])
    card = result.kept[0]
    assert (card.kind, card.answers) == ("name", ["mTOR"])


def test_receipt_source_quote_and_page_for_html(env):
    result, _ = env()
    for card, d in zip(result.kept, good_drafts()):
        assert card.receipt.source == SOURCE_ID
        assert card.receipt.quote == d["quote"]
        assert card.receipt.page == 1


def make_text_pdf(path: Path, texts: list[str]) -> Path:
    """A tiny PDF with one line of Helvetica text per page (copied from test_receipts)."""
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=900, height=200)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): writer._add_object(font)}
                )
            }
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    with path.open("wb") as f:
        writer.write(f)
    return path


def test_receipt_page_is_where_find_quote_finds_it_in_a_pdf(tmp_path):
    p1 = "Rapamycin is a drug that inhibits the kinase mTOR"
    p2 = "Rapamycin works by blocking mTORC1 signalling in cells"
    data = make_text_pdf(tmp_path / "made.pdf", [p1, p2]).read_bytes()
    sources_dir = tmp_path / "sources"
    pin_source(sources_dir, data, fmt="pdf", sid="pdf-src")
    ask, _ = fake_ask(
        [
            draft("what", "What does rapamycin inhibit?", quote=p1),
            draft("how", "How does rapamycin act in cells?", quote=p2),
        ]
    )
    result = block.write_cards(
        "rapamycin",
        "pdf-src",
        ask=ask,
        check=fake_check(),
        sources_dir=sources_dir,
        root=tmp_path,
        fetch=lambda url: data,
    )
    assert [c.receipt.page for c in result.kept] == [1, 2]


# -- Report and bar ------------------------------------------------------------------


def assert_counts_add_up(report, result):
    drops = (
        report.dropped_shape
        + report.dropped_link
        + report.dropped_quote
        + report.dropped_repeat
        + report.dropped_checker
        + report.dropped_ask
    )
    assert report.kept + drops == report.drafted
    assert report.kept == len(result.kept)
    assert drops == len(result.drops)


def test_good_run_passes_the_bar(env):
    result, _ = env()
    r = result.report
    assert (r.drafted, r.kept) == (4, 4)
    assert r.passed is True
    assert set(r.asks_kept) == {"what", "how", "how_sure", "catch"}
    assert r.asks_kept == sorted(set(r.asks_kept))
    assert r.prompt_version == block.PROMPT_VERSION
    assert_counts_add_up(r, result)


def test_passes_without_a_catch_card(env):
    result, _ = env(good_drafts()[:3])
    assert result.report.passed is True


def test_counts_add_up_with_every_kind_of_drop(env):
    fake = "Rapamycin doubled the lifespan of every human volunteer tested."
    drafts = [
        *good_drafts(),
        draft("what", question="Short"),
        draft("what", "What is fake about this one?", quote=fake),
        draft("how", "how does rapamycin SLOW cell growth?", quote=S_HOW),
        draft("what", "What breaks the checker here?", quote=S_WHAT),
        draft("what", "What errors in the checker here?", quote=S_WHAT),
    ]
    check = fake_check({"breaks the checker": 2, "errors in": ClaudeError("x")})
    result, _ = env(drafts, check=check, n=9)
    r = result.report
    assert r.drafted == 9
    assert (r.dropped_shape, r.dropped_quote, r.dropped_repeat) == (1, 1, 1)
    assert (r.dropped_checker, r.checker_errors) == (2, 1)
    assert_counts_add_up(r, result)


def test_passes_when_how_sure_missing(env):
    """New bar (2026-11-12): coverage is a topic goal over runs, not a run gate."""
    drafts = [d for d in good_drafts() if d["asks"] != "how_sure"]
    result, _ = env(drafts)
    assert "how_sure" not in result.report.asks_kept
    assert result.report.passed is True


def test_passes_when_only_one_ask_kept(env):
    drafts = [
        draft("what", "What does rapamycin inhibit in the cell?", quote=S_WHAT),
        draft("what", "What kind of molecule is rapamycin?", quote=S_WHAT),
    ]
    result, _ = env(drafts)
    assert result.report.asks_kept == ["what"]
    assert result.report.passed is True


def three_of_ten_quotes_missing(env):
    fake = "Rapamycin doubled the lifespan of every human volunteer tested."
    extra = [
        draft("what", f"What else is true of rapamycin, number {i}?", quote=S_WHAT)
        for i in range(3)
    ]
    missing = [
        draft("how", f"How does it work in people, number {i}?", quote=fake)
        for i in range(3)
    ]
    result, _ = env([*good_drafts(), *extra, *missing], n=10)
    return result


def test_fails_when_3_of_10_quotes_missing(env):
    """Fails even though 7 cards were kept: a writer inventing quotes isn't trusted."""
    result = three_of_ten_quotes_missing(env)
    r = result.report
    assert (r.drafted, r.kept, r.dropped_quote) == (10, 7, 3)
    assert r.passed is False


def test_two_of_10_quotes_missing_still_passes(env):
    fake = "Rapamycin doubled the lifespan of every human volunteer tested."
    extra = [
        draft("what", f"What else is true of rapamycin, number {i}?", quote=S_WHAT)
        for i in range(4)
    ]
    missing = [
        draft("how", f"How does it work in people, number {i}?", quote=fake)
        for i in range(2)
    ]
    result, _ = env([*good_drafts(), *extra, *missing], n=10)
    assert (result.report.drafted, result.report.dropped_quote) == (10, 2)
    assert result.report.passed is True


def test_passes_when_fewer_than_half_kept(env):
    """New bar: kept cards passed every gate, so a run keeping few still saves them."""
    bad = [
        draft("what", f"What breaks the checker, number {i}?", quote=S_WHAT)
        for i in range(5)
    ]
    result, _ = env([*good_drafts()[:3], *bad], check=fake_check({"breaks": 3}))
    r = result.report
    assert (r.drafted, r.kept) == (8, 3)
    assert r.passed is True


def test_passes_when_1_of_8_kept(env):
    bad = [
        draft("what", f"What breaks the checker, number {i}?", quote=S_WHAT)
        for i in range(7)
    ]
    result, _ = env([*good_drafts()[:1], *bad], check=fake_check({"breaks": 3}))
    r = result.report
    assert (r.drafted, r.kept, r.dropped_quote) == (8, 1, 0)
    assert r.passed is True


def test_exactly_half_kept_passes(env):
    bad = [
        draft("what", f"What breaks the checker, number {i}?", quote=S_WHAT)
        for i in range(4)
    ]
    result, _ = env([*good_drafts(), *bad], check=fake_check({"breaks": 3}))
    assert (result.report.drafted, result.report.kept) == (8, 4)
    assert result.report.passed is True


def test_zero_cards_gives_failing_report(env):
    result, _ = env([])
    assert result.report.drafted == 0
    assert result.kept == [] and result.drops == []
    assert result.report.passed is False


def test_every_draft_dropped_fails(env):
    result, _ = env(check=fake_check({"": 3}))
    assert result.kept == []
    assert result.report.passed is False


def test_report_model_dump_has_passed(env):
    result, _ = env()
    assert result.report.model_dump()["passed"] is True


# -- Errors --------------------------------------------------------------------------


def test_missing_source_record_raises_before_claude(env):
    ask, calls = fake_ask(good_drafts())
    with pytest.raises(FileNotFoundError):
        env(ask=ask, source_id="no-such-source")
    assert calls == []


def test_unfetchable_document_raises_before_claude(tmp_path):
    sources_dir = tmp_path / "sources"
    pin_source(sources_dir, html_doc())
    ask, calls = fake_ask(good_drafts())

    def broken(url):
        raise OSError("connection reset")

    with pytest.raises(DownloadError):
        block.write_cards(
            "rapamycin",
            SOURCE_ID,
            ask=ask,
            check=fake_check(),
            sources_dir=sources_dir,
            root=tmp_path,
            fetch=broken,
        )
    assert calls == []


def test_too_long_source_raises_before_claude(tmp_path):
    long_text = [S_WHAT] + ["Filler words about ageing research. " * 200] * 30
    data = html_doc(long_text)
    assert len(data) > 200_000
    sources_dir = tmp_path / "sources"
    pin_source(sources_dir, data)
    ask, calls = fake_ask(good_drafts())
    with pytest.raises(ValueError, match="source too long"):
        block.write_cards(
            "rapamycin",
            SOURCE_ID,
            ask=ask,
            check=fake_check(),
            sources_dir=sources_dir,
            root=tmp_path,
            fetch=lambda url: data,
        )
    assert calls == []


@pytest.mark.parametrize("n", [0, 21])
def test_n_out_of_range_raises(env, n):
    with pytest.raises(ValueError):
        env(n=n)


@pytest.mark.parametrize("n", [1, 20])
def test_n_at_the_limits_is_accepted(env, n):
    result, _ = env(n=n)
    assert result.report.drafted == min(n, 4)


@pytest.mark.parametrize("topic", ["!!!", "", "   "])
def test_empty_or_unsluggable_topic_raises(env, topic):
    with pytest.raises(ValueError):
        env(topic=topic)


BAD_REPLIES = {
    "not json": "this is not json",
    "not an object": json.dumps([1, 2]),
    "no cards key": json.dumps({"drafts": []}),
    "cards not a list": json.dumps({"cards": "none"}),
    "draft missing quote": json.dumps(
        {"cards": [{k: v for k, v in draft().items() if k != "quote"}]}
    ),
    "unknown asks": json.dumps({"cards": [draft(asks="who")]}),
    "unknown kind": json.dumps({"cards": [draft(kind="trivia")]}),
}


@pytest.mark.parametrize("text", BAD_REPLIES.values(), ids=BAD_REPLIES.keys())
def test_bad_reply_raises_claude_error(env, text):
    ask, _ = fake_ask(text=text)
    with pytest.raises(ClaudeError, match="bad reply"):
        env(ask=ask)


def test_claude_error_from_ask_propagates(env):
    ask, _ = fake_ask(raises=ClaudeError("claude not found"))
    with pytest.raises(ClaudeError):
        env(ask=ask)


def test_more_than_n_drafts_only_first_n_used(env):
    check = fake_check()
    result, _ = env(good_drafts(), n=2, check=check)
    assert result.report.drafted == 2
    assert [c.question for c in result.kept] == [
        d["question"] for d in good_drafts()[:2]
    ]
    assert len(check.calls) == 2


def test_draft_model_accepts_a_valid_draft():
    d = block.Draft.model_validate(draft("how_sure", quote=S_SURE))
    assert (d.asks, d.kind, d.quote) == ("how_sure", "fact", S_SURE)


# -- CLI -----------------------------------------------------------------------------


@pytest.fixture
def results(env):
    """Genuine WriterResults from write_cards: passing, failing-with-kept, empty."""
    passing, _ = env()
    failing = three_of_ten_quotes_missing(env)  # misses the bar with 7 kept
    empty, _ = env(check=fake_check({"": 3}))
    assert passing.report.passed and not failing.report.passed and not empty.kept
    return {"pass": passing, "fail": failing, "empty": empty}


@pytest.fixture
def cli(tmp_path, monkeypatch):
    """Run the CLI with a fake write_cards and a temp CARDS_DIR."""
    from longevity_trainer import cli as cli_module

    cards_dir = tmp_path / "cards"
    cards_dir.mkdir()
    monkeypatch.setattr(cli_module, "CARDS_DIR", cards_dir)
    calls: list = []

    def run(result, *args):
        def fake_write_cards(*a, **k):
            calls.append((a, k))
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(cli_module, "write_cards", fake_write_cards)
        argv = ["write-cards", "--topic", "rapamycin", "--source", SOURCE_ID, *args]
        return cli_module.main(argv)

    run.cards_dir = cards_dir
    run.calls = calls
    return run


def test_cli_writes_kept_cards_and_they_load_back(cli, results):
    assert cli(results["pass"]) == 0
    out = cli.cards_dir / "rapamycin.jsonl"
    assert out.exists()
    loaded = load_cards(cli.cards_dir)
    assert [c.id for c in loaded] == [c.id for c in results["pass"].kept]
    assert loaded == results["pass"].kept


def test_cli_file_name_uses_the_topic_slug(cli, results, monkeypatch):
    from longevity_trainer import cli as cli_module

    monkeypatch.setattr(cli_module, "write_cards", lambda *a, **k: results["pass"])
    argv = ["write-cards", "--topic", "Epigenetic clocks!", "--source", SOURCE_ID]
    assert cli_module.main(argv) == 0
    assert (cli.cards_dir / "epigenetic-clocks.jsonl").exists()


def test_cli_dry_run_writes_nothing(cli, results):
    assert cli(results["pass"], "--dry-run") == 0
    assert len(cli.calls) == 1  # still drafts
    assert list(cli.cards_dir.iterdir()) == []


def test_cli_existing_file_without_add_or_replace_exits_1_before_drafting(
    cli, results, capsys
):
    out = cli.cards_dir / "rapamycin.jsonl"
    out.write_text("old\n", encoding="utf-8")
    assert cli(results["pass"]) == 1
    assert cli.calls == []
    assert out.read_text(encoding="utf-8") == "old\n"
    captured = capsys.readouterr()
    text = captured.out + captured.err
    assert "--add" in text and "--replace" in text


def test_cli_replace_overwrites_existing_file(cli, results):
    out = cli.cards_dir / "rapamycin.jsonl"
    out.write_text("old\n", encoding="utf-8")
    assert cli(results["pass"], "--replace") == 0
    assert [c.id for c in load_cards(cli.cards_dir)] == [
        c.id for c in results["pass"].kept
    ]


def test_cli_exit_1_when_report_fails(cli, results):
    assert cli(results["fail"]) == 1
    assert list(cli.cards_dir.iterdir()) == []  # writes only when the report passes


def test_cli_nothing_kept_exits_1_and_writes_nothing(cli, results):
    assert cli(results["empty"]) == 1
    assert list(cli.cards_dir.iterdir()) == []


def test_cli_passes_n_and_model(cli, results):
    cli(results["pass"], "--n", "5", "--model", "haiku", "--dry-run")
    ((_args, kwargs),) = cli.calls
    assert kwargs.get("n") == 5
    assert kwargs.get("model") == "haiku"


@pytest.mark.parametrize(
    "error", [FileNotFoundError("no source record"), DownloadError("bad download")]
)
def test_cli_source_error_prints_one_line_exit_1(cli, capsys, error):
    assert cli(error) == 1
    captured = capsys.readouterr()
    assert str(error) in captured.out + captured.err
    assert list(cli.cards_dir.iterdir()) == []


def test_cli_prints_a_line_per_draft_and_the_report(cli, results, capsys):
    cli(results["pass"], "--dry-run")
    out = capsys.readouterr().out
    for card in results["pass"].kept:
        assert card.question in out
    assert results["pass"].report.prompt_version in out


# ---- Added after the SPEC review (PROMPT_VERSION 3, page markers, CLI bank) -------


def test_prompt_version_is_7():
    """v7 added the learner's level and `only_asks` (SPEC 2026-11-18)."""
    assert block.PROMPT_VERSION == "7"


def test_checker_rejected_question_does_not_block_a_later_same_question(env):
    first = draft("what", "What breaks the checker for rapamycin?", quote=S_WHAT)
    again = draft("what", "  what BREAKS the checker for   rapamycin? ", quote=S_WHAT)
    answers = iter([CardVerdict(ok=False, rules=[3], reason="breaks rule 3")])
    seen: list[str] = []

    def check(card, **kwargs):
        seen.append(card.question)
        return next(answers, CardVerdict(ok=True, rules=[], reason="fine"))

    result, _ = env([first, *good_drafts(), again], check=check)
    assert gates(result) == ["checker"]
    assert len(seen) == 6  # the second wording was checked, not dropped as repeat
    assert result.report.dropped_repeat == 0
    assert result.kept[-1].question.strip().lower().startswith("what breaks")


def test_checker_error_question_does_not_block_a_later_same_question(env):
    first = draft("what", "What errors in the checker today?", quote=S_WHAT)
    again = draft("what", "WHAT errors in the  checker today?", quote=S_WHAT)
    calls = {"n": 0}

    def check(card, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ClaudeError("timed out")
        return CardVerdict(ok=True, rules=[], reason="fine")

    result, _ = env([first, *good_drafts(), again], check=check)
    assert gates(result) == ["checker"]
    assert result.report.checker_errors == 1
    assert result.report.dropped_repeat == 0
    assert calls["n"] == 6
    assert len(result.kept) == 5


def test_one_page_source_has_no_page_marker(env):
    _, calls = env()
    assert "[page" not in calls[0]["prompt"]


def test_two_page_source_marks_each_page(tmp_path):
    p1 = "Rapamycin is a drug that inhibits the kinase mTOR"
    p2 = "Rapamycin works by blocking mTORC1 signalling in cells"
    data = make_text_pdf(tmp_path / "made.pdf", [p1, p2]).read_bytes()
    sources_dir = tmp_path / "sources"
    pin_source(sources_dir, data, fmt="pdf", sid="pdf-src")
    ask, calls = fake_ask(good_drafts())
    block.write_cards(
        "rapamycin",
        "pdf-src",
        ask=ask,
        check=fake_check(),
        sources_dir=sources_dir,
        root=tmp_path,
        fetch=lambda url: data,
    )
    prompt = calls[0]["prompt"]
    i1, t1, i2, t2 = (prompt.find(s) for s in ("[page 1]", p1, "[page 2]", p2))
    assert -1 not in (i1, t1, i2, t2)
    assert i1 < t1 < i2 < t2


def test_record_with_other_id_raises_before_claude(tmp_path):
    sources_dir = tmp_path / "sources"
    data = html_doc()
    pin_source(sources_dir, data, sid="other-id")
    (sources_dir / "other-id.json").rename(sources_dir / f"{SOURCE_ID}.json")
    ask, calls = fake_ask(good_drafts())
    with pytest.raises(ValueError, match="other-id"):
        block.write_cards(
            "rapamycin",
            SOURCE_ID,
            ask=ask,
            check=fake_check(),
            sources_dir=sources_dir,
            root=tmp_path,
            fetch=lambda url: data,
        )
    assert calls == []


def write_card_file(path: Path, cards) -> None:
    path.write_text(
        "".join(c.model_dump_json() + "\n" for c in cards), encoding="utf-8"
    )


def renamed(cards, prefix: str):
    return [c.model_copy(update={"id": f"{prefix}-{i}"}) for i, c in enumerate(cards)]


def test_cli_dry_run_with_existing_file_still_drafts_and_writes_nothing(cli, results):
    out = cli.cards_dir / "rapamycin.jsonl"
    write_card_file(out, old_cards(results["pass"].kept))
    before = out.read_text(encoding="utf-8")
    cli(results["pass"], "--dry-run")
    assert len(cli.calls) == 1
    assert out.read_text(encoding="utf-8") == before
    assert [p.name for p in cli.cards_dir.iterdir()] == ["rapamycin.jsonl"]


def test_cli_taken_ids_are_other_files_not_the_topics_own(cli, results):
    kept = results["pass"].kept
    write_card_file(cli.cards_dir / "aaa.jsonl", renamed(kept[:2], "other"))
    write_card_file(cli.cards_dir / "rapamycin.jsonl", kept)
    assert cli(results["pass"], "--replace") == 0
    ((_args, kwargs),) = cli.calls
    assert set(kwargs["taken_ids"]) == {"other-0", "other-1"}
    assert "ask" in kwargs and "check" in kwargs


def test_cli_bad_line_in_other_card_file_exits_1_before_drafting(cli, results):
    (cli.cards_dir / "aaa.jsonl").write_text("not json\n", encoding="utf-8")
    assert cli(results["pass"]) == 1
    assert cli.calls == []
    assert not (cli.cards_dir / "rapamycin.jsonl").exists()


def test_cli_broken_topic_file_is_replaced(cli, results):
    out = cli.cards_dir / "rapamycin.jsonl"
    out.write_text("this is broken {\n", encoding="utf-8")
    assert cli(results["pass"], "--replace") == 0
    assert len(cli.calls) == 1
    assert [c.id for c in load_cards(cli.cards_dir)] == [
        c.id for c in results["pass"].kept
    ]


def test_cli_leaves_no_tmp_file(cli, results):
    assert cli(results["pass"]) == 0
    assert [p.name for p in cli.cards_dir.iterdir()] == ["rapamycin.jsonl"]


def test_cli_prints_claude_calls_line(cli, results, capsys):
    cli(results["pass"], "--dry-run")
    assert "Claude calls" in capsys.readouterr().out


# ---- Added for `pages` (SPEC: Inputs row, Receipts, CLI `--pages`) ------------------

PAGE_1 = "Rapamycin is a drug that inhibits the kinase mTOR"
PAGE_2 = "Rapamycin works by blocking mTORC1 signalling in cells"
PAGE_3 = "In mice rapamycin extended lifespan but human data are few"


def test_block_spec_lists_pages_input():
    assert "pages" in block.BLOCK_SPEC.inputs


@pytest.fixture
def paged(tmp_path):
    """A pinned 3-page PDF source; `run(drafts, pages=..., texts=...)` calls write_cards."""

    def run(drafts=None, texts=(PAGE_1, PAGE_2, PAGE_3), ask=None, **kwargs):
        data = make_text_pdf(tmp_path / "paged.pdf", list(texts)).read_bytes()
        sources_dir = tmp_path / "sources"
        pin_source(sources_dir, data, fmt="pdf", sid="paged-src")
        calls = None
        if ask is None:
            ask, calls = fake_ask(drafts or [])
        result = block.write_cards(
            "rapamycin",
            "paged-src",
            ask=ask,
            check=fake_check(),
            sources_dir=sources_dir,
            root=tmp_path,
            fetch=lambda url: data,
            **kwargs,
        )
        return result, calls

    return run


def test_pages_prompt_has_only_chosen_pages_with_real_numbers(paged):
    _, calls = paged(pages=(2, 3))
    prompt = calls[0]["prompt"]
    assert PAGE_1 not in prompt
    assert "[page 1]" not in prompt
    i2, t2, i3, t3 = (prompt.find(s) for s in ("[page 2]", PAGE_2, "[page 3]", PAGE_3))
    assert -1 not in (i2, t2, i3, t3)
    assert i2 < t2 < i3 < t3


def test_pages_quote_only_on_an_unchosen_page_dropped_at_quote(paged):
    drafts = [
        draft("what", "What does rapamycin inhibit?", quote=PAGE_1),
        draft("how", "How does rapamycin act in cells?", quote=PAGE_2),
    ]
    result, _ = paged(drafts, pages=(2, 3))
    assert gates(result) == ["quote"]
    assert result.drops[0].question == "What does rapamycin inhibit?"
    assert [c.question for c in result.kept] == ["How does rapamycin act in cells?"]


def test_pages_receipt_page_is_the_real_page_number(paged):
    drafts = [
        draft("how", "How does rapamycin act in cells?", quote=PAGE_2),
        draft("how_sure", "How strong is the lifespan evidence?", quote=PAGE_3),
    ]
    result, _ = paged(drafts, pages=(2, 3))
    assert [c.receipt.page for c in result.kept] == [2, 3]


def test_pages_single_page_sends_one_page_without_marker(paged):
    _, calls = paged(pages=(2, 2))
    prompt = calls[0]["prompt"]
    assert PAGE_2 in prompt
    assert PAGE_1 not in prompt and PAGE_3 not in prompt
    assert "[page" not in prompt


def test_pages_none_sends_the_whole_source(paged):
    _, calls = paged(pages=None)
    prompt = calls[0]["prompt"]
    for text in (PAGE_1, PAGE_2, PAGE_3):
        assert text in prompt


@pytest.mark.parametrize("pages", [(0, 1), (2, 1), (1, 4)])
def test_pages_out_of_range_raises_naming_page_count_before_claude(paged, pages):
    ask, calls = fake_ask(good_drafts())
    with pytest.raises(ValueError, match="3"):
        paged(ask=ask, pages=pages)
    assert calls == []


def test_pages_size_limit_is_on_the_chosen_pages_only(paged):
    filler = "Filler words about ageing research " * 6000
    assert len(filler) > 200_000
    _, calls = paged(texts=(filler, PAGE_2, PAGE_3), pages=(2, 3))
    assert len(calls) == 1
    assert PAGE_2 in calls[0]["prompt"]


def test_pages_whole_source_over_limit_still_raises(paged):
    filler = "Filler words about ageing research " * 6000
    ask, calls = fake_ask(good_drafts())
    with pytest.raises(ValueError, match="source too long"):
        paged(ask=ask, texts=(filler, PAGE_2, PAGE_3))
    assert calls == []


# -- CLI `--pages` -------------------------------------------------------------------


@pytest.mark.parametrize("flag, expected", [("17-20", (17, 20)), ("5", (5, 5))])
def test_cli_pages_flag_is_passed_as_a_tuple(cli, results, flag, expected):
    cli(results["pass"], "--pages", flag, "--dry-run")
    ((_args, kwargs),) = cli.calls
    assert tuple(kwargs["pages"]) == expected


def test_cli_without_pages_passes_none(cli, results):
    cli(results["pass"], "--dry-run")
    ((_args, kwargs),) = cli.calls
    assert kwargs.get("pages") is None


@pytest.mark.parametrize("flag", ["x", "5-", "0-3", "9-4"])
def test_cli_bad_pages_exits_2_without_calling_write_cards(cli, results, flag):
    with pytest.raises(SystemExit) as exc:
        cli(results["pass"], "--pages", flag, "--dry-run")
    assert exc.value.code == 2
    assert cli.calls == []


# ---- Added for the new bar, `taken_questions` and `--add` (SPEC 2026-11-12) -------


def test_taken_question_dropped_at_repeat_before_the_checker(env):
    check = fake_check()
    taken = {"  what DOES rapamycin   inhibit in the CELL? "}
    result, _ = env(check=check, taken_questions=taken)
    assert gates(result) == ["repeat"]
    assert "already in the bank" in result.drops[0].reason
    assert result.drops[0].question == good_drafts()[0]["question"]
    assert result.report.dropped_repeat == 1
    assert good_drafts()[0]["question"] not in [c.question for c in check.calls]
    assert len(check.calls) == 3


def test_repeat_within_run_says_earlier_card(env):
    first = draft("what", "What does rapamycin inhibit?", quote=S_WHAT)
    again = draft("what", "WHAT does rapamycin  inhibit?", quote=S_WHAT)
    result, _ = env([first, again])
    assert gates(result) == ["repeat"]
    assert "same question as an earlier card" in result.drops[0].reason


def test_taken_questions_default_is_empty(env):
    result, _ = env()
    assert result.report.dropped_repeat == 0


def old_cards(kept, n: int = 2):
    """Cards for an existing topic file: ids and questions unlike the new ones."""
    return [
        c.model_copy(
            update={"id": f"rapamycin-old-{i}", "question": f"Old question {i}?"}
        )
        for i, c in enumerate(kept[:n])
    ]


def test_cli_add_keeps_old_lines_first_and_appends(cli, results):
    out = cli.cards_dir / "rapamycin.jsonl"
    old = old_cards(results["pass"].kept)
    write_card_file(out, old)
    old_text = out.read_text(encoding="utf-8")
    assert cli(results["pass"], "--add") == 0
    assert out.read_text(encoding="utf-8").startswith(old_text)
    loaded = load_cards(cli.cards_dir)
    assert [c.id for c in loaded] == [c.id for c in old] + [
        c.id for c in results["pass"].kept
    ]
    assert [p.name for p in cli.cards_dir.iterdir()] == ["rapamycin.jsonl"]


def test_cli_add_taken_includes_topic_file_and_other_files(cli, results):
    kept = results["pass"].kept
    other = [
        c.model_copy(update={"id": "other-0", "question": "Other question zero?"})
        for c in kept[:1]
    ]
    write_card_file(cli.cards_dir / "aaa.jsonl", other)
    write_card_file(cli.cards_dir / "rapamycin.jsonl", old_cards(kept))
    assert cli(results["pass"], "--add") == 0
    ((_args, kwargs),) = cli.calls
    assert set(kwargs["taken_ids"]) == {"other-0", "rapamycin-old-0", "rapamycin-old-1"}
    assert set(kwargs["taken_questions"]) == {
        "Other question zero?",
        "Old question 0?",
        "Old question 1?",
    }


def test_cli_without_add_taken_questions_are_other_files_only(cli, results):
    kept = results["pass"].kept
    other = [
        c.model_copy(update={"id": "other-0", "question": "Other question zero?"})
        for c in kept[:1]
    ]
    write_card_file(cli.cards_dir / "aaa.jsonl", other)
    write_card_file(cli.cards_dir / "rapamycin.jsonl", old_cards(kept))
    assert cli(results["pass"], "--replace") == 0
    ((_args, kwargs),) = cli.calls
    assert set(kwargs["taken_questions"]) == {"Other question zero?"}
    assert set(kwargs["taken_ids"]) == {"other-0"}


def test_cli_no_cards_yet_passes_empty_taken_questions(cli, results):
    cli(results["pass"], "--dry-run")
    ((_args, kwargs),) = cli.calls
    assert set(kwargs.get("taken_questions") or set()) == set()


def test_cli_add_with_no_file_yet_writes_it(cli, results):
    assert cli(results["pass"], "--add") == 0
    assert [c.id for c in load_cards(cli.cards_dir)] == [
        c.id for c in results["pass"].kept
    ]


def test_cli_add_and_replace_together_exit_2(cli, results):
    with pytest.raises(SystemExit) as exc:
        cli(results["pass"], "--add", "--replace")
    assert exc.value.code == 2
    assert cli.calls == []


def test_cli_add_with_broken_topic_file_exits_1_before_drafting(cli, results):
    out = cli.cards_dir / "rapamycin.jsonl"
    out.write_text("this is broken {\n", encoding="utf-8")
    assert cli(results["pass"], "--add") == 1
    assert cli.calls == []
    assert out.read_text(encoding="utf-8") == "this is broken {\n"


def test_cli_add_when_report_fails_leaves_file_unchanged(cli, results):
    out = cli.cards_dir / "rapamycin.jsonl"
    write_card_file(out, old_cards(results["pass"].kept))
    before = out.read_text(encoding="utf-8")
    assert cli(results["fail"], "--add") == 1
    assert out.read_text(encoding="utf-8") == before


def missing_part(out: str) -> str:
    """The text after "missing" on the coverage line."""
    lines = [ln for ln in out.splitlines() if "missing" in ln.lower()]
    assert lines, f"no coverage line saying what's missing in:\n{out}"
    return lines[-1].lower().split("missing", 1)[1]


def test_cli_coverage_line_names_what_is_missing(cli, env, capsys):
    drafts = [
        draft("what", "What does rapamycin inhibit in the cell?", quote=S_WHAT),
        draft("how_sure", "How strong is the lifespan evidence?", quote=S_SURE),
    ]
    result, _ = env(drafts)
    assert [c.id for c in result.kept] == ["rapamycin-what-1", "rapamycin-how-sure-1"]
    assert cli(result) == 0
    out = capsys.readouterr().out
    tail = missing_part(out)
    assert re.search(r"\bhow\b(?![_-]sure)", tail)
    assert "what" not in tail
    assert "sure" not in tail
    assert "catch" not in tail  # catch is covered-or-not, never "missing"
    assert "run again with --add --ask how" in out
    assert coverage_line(out).count("--ask") == 1


def test_cli_coverage_counts_the_existing_file_with_add(cli, env, capsys):
    """Old file has how; new run adds what + how_sure: nothing of the three missing."""
    result, _ = env(
        [
            draft("what", "What does rapamycin inhibit in the cell?", quote=S_WHAT),
            draft("how_sure", "How strong is the lifespan evidence?", quote=S_SURE),
        ]
    )
    how = env([draft("how", "How does rapamycin slow cell growth?", quote=S_HOW)])[0]
    old = [how.kept[0].model_copy(update={"id": "rapamycin-how-7"})]
    write_card_file(cli.cards_dir / "rapamycin.jsonl", old)
    assert cli(result, "--add") == 0
    out = capsys.readouterr().out
    missing_lines = [
        ln.lower().split("missing", 1)[1]
        for ln in out.splitlines()
        if "missing" in ln.lower()
    ]
    for tail in missing_lines:
        assert not re.search(r"\b(what|how|how[_-]sure)\b", tail)


# ---- Added after the SPEC review (PROMPT_VERSION 4, one read, coverage) -----------


def test_asks_are_the_five_in_order():
    assert block.ASKS == ("what", "how", "how_sure", "catch", "connect")


def test_required_asks_are_what_how_how_sure():
    assert block.REQUIRED_ASKS == {"what", "how", "how_sure"}


def test_prompt_lists_every_taken_question(env):
    taken = {"Which enzyme does metformin target?", "What is a senolytic drug?"}
    _, calls = env(taken_questions=taken)
    prompt = calls[0]["prompt"]
    for q in taken:
        assert q in prompt
    assert "bank" in prompt.lower()


def test_prompt_has_no_taken_list_without_taken_questions(env):
    """Assumes the list's heading mentions "the bank" (SPEC: "already in the bank")."""
    _, calls = env()
    assert "bank" not in calls[0]["prompt"].lower()


def test_pages_receipt_page_is_first_page_in_whole_source(paged):
    d = draft("what", "What does rapamycin inhibit?", quote=PAGE_1)
    result, _ = paged([d], texts=(PAGE_1, PAGE_2, PAGE_1), pages=(3, 3))
    assert gates(result) == []
    assert [c.receipt.page for c in result.kept] == [1]


def test_pages_quote_only_on_page_1_dropped_with_pages_3(paged):
    d = draft("what", "What does rapamycin inhibit?", quote=PAGE_1)
    result, _ = paged([d], pages=(3, 3))
    assert gates(result) == ["quote"]
    assert result.kept == []


def test_kept_0_with_every_draft_dropped_at_shape_fails(env):
    drafts = [
        draft(a, question="Why??", quote=q)
        for a, q in zip(
            ["what", "how", "how_sure", "catch"], [S_WHAT, S_HOW, S_SURE, S_CATCH]
        )
    ]
    result, _ = env(drafts)
    assert gates(result) == ["shape"] * 4
    assert result.report.kept == 0
    assert result.report.dropped_quote == 0
    assert result.report.passed is False


def what_and_how_sure(env):
    result, _ = env(
        [
            draft("what", "What does rapamycin inhibit in the cell?", quote=S_WHAT),
            draft("how_sure", "How strong is the lifespan evidence?", quote=S_SURE),
        ]
    )
    return result


def how_file(env, cli):
    """A topic file with one valid -how- card; returns its path."""
    how = env([draft("how", "How does rapamycin slow cell growth?", quote=S_HOW)])[0]
    card = how.kept[0].model_copy(update={"id": "rapamycin-how-7"})
    out = cli.cards_dir / "rapamycin.jsonl"
    write_card_file(out, [card])
    return out, card


def test_cli_dry_run_counts_existing_file_like_add(cli, env, capsys):
    """Dry run, no --add: the file's how card counts, and its id/question are taken."""
    _, card = how_file(env, cli)
    assert cli(what_and_how_sure(env), "--dry-run") == 0
    ((_args, kwargs),) = cli.calls
    assert "rapamycin-how-7" in set(kwargs["taken_ids"])
    assert card.question in set(kwargs["taken_questions"])
    out = capsys.readouterr().out
    for ln in out.splitlines():
        if "missing" in ln.lower():
            tail = ln.lower().split("missing", 1)[1]
            assert not re.search(r"\b(what|how|how[_-]sure)\b", tail)


def test_cli_replace_coverage_counts_only_kept_cards(cli, env, capsys):
    how_file(env, cli)
    assert cli(what_and_how_sure(env), "--replace") == 0
    tail = missing_part(capsys.readouterr().out)
    assert re.search(r"\bhow\b(?![_-]sure)", tail)


def test_cli_failing_run_still_prints_coverage_of_unchanged_file(
    cli, env, results, capsys
):
    """File has only how; the failing run's kept cards don't count."""
    out, _ = how_file(env, cli)
    before = out.read_text(encoding="utf-8")
    assert cli(results["fail"], "--add") == 1
    assert out.read_text(encoding="utf-8") == before
    tail = missing_part(capsys.readouterr().out)
    assert "what" in tail
    assert re.search(r"how[_ -]sure", tail)


def test_cli_failing_run_with_no_file_prints_coverage(cli, results, capsys):
    assert cli(results["fail"]) == 1
    out = capsys.readouterr().out
    tail = missing_part(out)
    assert "what" in tail and re.search(r"how[_ -]sure", tail)
    assert "run again with --add --ask what --ask how --ask how_sure" in out


def test_cli_failed_write_prints_no_coverage_line(cli, env, capsys):
    """The <file>.tmp path is a folder, so the write fails: exit 1, no coverage."""
    (cli.cards_dir / "rapamycin.jsonl.tmp").mkdir()
    assert cli(what_and_how_sure(env)) == 1
    captured = capsys.readouterr()
    assert not (cli.cards_dir / "rapamycin.jsonl").exists()
    text = captured.out + captured.err
    assert not [ln for ln in text.splitlines() if "missing" in ln.lower()]


def test_cli_topic_file_changed_during_run_writes_nothing(
    cli, env, results, monkeypatch, capsys
):
    from longevity_trainer import cli as cli_module

    out, card = how_file(env, cli)
    edited = card.model_copy(
        update={"id": "rapamycin-how-8", "question": "An edited question here?"}
    )

    def fake_write_cards(*a, **k):
        write_card_file(out, [card, edited])  # another run / a hand edit
        return results["pass"]

    monkeypatch.setattr(cli_module, "write_cards", fake_write_cards)
    argv = ["write-cards", "--topic", "rapamycin", "--source", SOURCE_ID, "--add"]
    assert cli_module.main(argv) == 1
    after_edit = out.read_text(encoding="utf-8")
    assert [c.id for c in load_cards(cli.cards_dir)] == [
        "rapamycin-how-7",
        "rapamycin-how-8",
    ]
    assert after_edit.count("\n") == 2
    captured = capsys.readouterr()
    assert "changed" in (captured.out + captured.err).lower()
    assert [p.name for p in cli.cards_dir.iterdir()] == ["rapamycin.jsonl"]


# ---- Added for connect cards (SPEC 2026-11-13, PROMPT_VERSION 5) -------------------

TOPICS = {
    "mtor": "mTOR: the cell's growth switch",
    "ampk": "AMPK: the energy-shortage sensor",
    "rapamycin": "Rapamycin: mechanism, mouse evidence, human trials",
}
CONNECT_Q = "Which cell growth switch does rapamycin turn down?"


def connect(links_to="mtor", question=CONNECT_Q, quote=S_WHAT, asks="connect"):
    d = draft(asks, question, answers=["mTOR"], quote=quote, kind="name")
    d["links_to"] = links_to
    return d


def test_block_spec_lists_topics_input_and_new_outputs():
    assert "topics" in block.BLOCK_SPEC.inputs
    assert {"TOPICS_FILE", "load_topics"} <= set(block.BLOCK_SPEC.outputs)


def test_connect_draft_with_known_topic_is_kept(env):
    result, _ = env([*good_drafts(), connect()], topics=TOPICS)
    assert gates(result) == []
    assert result.kept[-1].id == "rapamycin-connect-1"
    assert "connect" in result.report.asks_kept
    assert result.report.dropped_link == 0


def test_connect_links_to_with_spaces_is_kept(env):
    result, _ = env([connect(" mtor ")], topics=TOPICS)
    assert gates(result) == []
    assert [c.id for c in result.kept] == ["rapamycin-connect-1"]


@pytest.mark.parametrize(
    "links_to, reason",
    [
        ("", "has no links_to"),
        ("   ", "has no links_to"),
        ("made-up", "not a known topic"),
        ("rapamycin", "own topic"),
    ],
)
def test_connect_bad_links_to_dropped_at_link(env, links_to, reason):
    result, _ = env([*good_drafts(), connect(links_to)], topics=TOPICS)
    assert gates(result) == ["link"]
    assert reason in result.drops[0].reason
    assert result.drops[0].question == CONNECT_Q
    assert result.report.dropped_link == 1


def test_unknown_links_to_reason_names_it(env):
    result, _ = env([connect("made-up")], topics=TOPICS)
    assert "'made-up'" in result.drops[0].reason


def test_own_topic_is_the_topic_slug(env):
    """links_to == slug(topic): "Rapamycin!" has slug "rapamycin"."""
    result, _ = env([connect("rapamycin")], topic="Rapamycin!", topics=TOPICS)
    assert gates(result) == ["link"]
    assert "own topic" in result.drops[0].reason


def test_non_connect_draft_with_links_to_dropped_at_link(env):
    d = connect(
        "mtor", question="What does rapamycin inhibit in the cell?", asks="what"
    )
    result, _ = env([d], topics=TOPICS)
    assert gates(result) == ["link"]
    assert "only connect cards" in result.drops[0].reason


def test_non_connect_draft_with_blank_links_to_is_fine(env):
    d = connect("  ", question="What does rapamycin inhibit in the cell?", asks="what")
    result, _ = env([d], topics=TOPICS)
    assert gates(result) == []


def test_quote_gate_comes_before_link(env):
    """An invented quote always counts against the bar, even with a bad link."""
    fake = "Rapamycin doubled the lifespan of every human volunteer tested."
    result, _ = env([connect("made-up", quote=fake)], topics=TOPICS)
    assert gates(result) == ["quote"]
    assert (result.report.dropped_quote, result.report.dropped_link) == (1, 0)


def test_link_gate_comes_before_checker(env):
    check = fake_check()
    result, _ = env([connect("made-up")], topics=TOPICS, check=check)
    assert gates(result) == ["link"]
    assert check.calls == []


def test_system_prompt_asks_for_connect_cards(env):
    _, calls = env(topics=TOPICS)
    system = calls[0]["system"]
    assert "connect" in system and "links_to" in system
    assert "at least one connect card" in system


def test_link_gate_comes_after_shape(env):
    result, _ = env([connect("made-up", question="Why??")], topics=TOPICS)
    assert gates(result) == ["shape"]


def test_counts_add_up_with_a_link_drop(env):
    drafts = [*good_drafts(), connect("made-up"), connect()]
    result, _ = env(drafts, topics=TOPICS, n=6)
    r = result.report
    assert (r.drafted, r.kept, r.dropped_link) == (6, 5, 1)
    assert_counts_add_up(r, result)
    assert "dropped_link" in r.model_dump()


def test_prompt_lists_topics_but_not_own_topic(env):
    _, calls = env(topics=TOPICS)
    prompt = calls[0]["prompt"]
    assert "- mtor: mTOR: the cell's growth switch" in prompt
    assert "- ampk: AMPK: the energy-shortage sensor" in prompt
    assert "- rapamycin:" not in prompt


def test_required_asks_do_not_include_connect():
    assert "connect" not in block.REQUIRED_ASKS
    assert block.ASKS[-1] == "connect"


def test_draft_without_links_to_reads_as_blank():
    d = block.Draft.model_validate(draft("how_sure", quote=S_SURE))
    assert d.links_to == ""


def test_draft_accepts_connect_with_links_to():
    d = block.Draft.model_validate(connect())
    assert (d.asks, d.links_to) == ("connect", "mtor")


def test_reply_schema_requires_links_to_and_allows_connect(env):
    _, calls = env(topics=TOPICS)
    items = calls[0]["json_schema"]["properties"]["cards"]["items"]
    assert "links_to" in items["required"]
    assert "connect" in json.dumps(items)


def test_topics_none_uses_load_topics_from_topics_file(env, tmp_path, monkeypatch):
    f = tmp_path / "topics.jsonl"
    f.write_text(
        json.dumps({"id": "zzz-topic", "topic": "A test topic", "status": "v1"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(block, "TOPICS_FILE", f)
    other = connect("mtor", question="Which growth switch is blocked by rapamycin?")
    result, calls = env([connect("zzz-topic"), other], topics=None)
    assert "- zzz-topic: A test topic" in calls[0]["prompt"]
    assert [c.id for c in result.kept] == ["rapamycin-connect-1"]
    assert gates(result) == ["link"]  # mtor isn't in this topics file


def test_missing_topics_file_raises_before_claude(env, tmp_path, monkeypatch):
    monkeypatch.setattr(block, "TOPICS_FILE", tmp_path / "nope.jsonl")
    ask, calls = fake_ask(good_drafts())
    with pytest.raises(FileNotFoundError):
        env(ask=ask, topics=None)
    assert calls == []


def test_bad_topics_file_raises_before_claude(env, tmp_path, monkeypatch):
    f = tmp_path / "topics.jsonl"
    f.write_text("not json\n", encoding="utf-8")
    monkeypatch.setattr(block, "TOPICS_FILE", f)
    ask, calls = fake_ask(good_drafts())
    with pytest.raises(ValueError):
        env(ask=ask, topics=None)
    assert calls == []


# -- load_topics ---------------------------------------------------------------------


def topic_line(tid, text="Some topic", status="v1") -> str:
    return json.dumps({"id": tid, "topic": text, "status": status})


def test_topics_file_is_data_topics_jsonl():
    assert block.TOPICS_FILE == ROOT / "data" / "topics.jsonl"


def test_load_topics_keeps_v1_in_file_order_and_skips_blanks(tmp_path):
    f = tmp_path / "topics.jsonl"
    lines = [
        topic_line("b-one", "B one"),
        "",
        topic_line("later", "Later", status="after-m5"),
        "   ",
        topic_line("a-two", "A two"),
        topic_line("read-only", "Read", status="read"),
    ]
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    topics = block.load_topics(f)
    assert topics == {"b-one": "B one", "a-two": "A two"}
    assert list(topics) == ["b-one", "a-two"]


def test_load_topics_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        block.load_topics(tmp_path / "nope.jsonl")


BAD_TOPIC_LINES = {
    "not json": "not json",
    "not an object": "[1, 2]",
    "no id": json.dumps({"topic": "T", "status": "v1"}),
    "no topic": json.dumps({"id": "x", "status": "v1"}),
    "no status": json.dumps({"id": "x", "topic": "T"}),
    "id not a string": json.dumps({"id": 5, "topic": "T", "status": "v1"}),
    "topic not a string": json.dumps({"id": "x", "topic": ["T"], "status": "v1"}),
    "status not a string": json.dumps({"id": "x", "topic": "T", "status": 1}),
}


@pytest.mark.parametrize("bad", BAD_TOPIC_LINES.values(), ids=BAD_TOPIC_LINES.keys())
def test_load_topics_bad_line_raises_naming_line_number(tmp_path, bad):
    f = tmp_path / "topics.jsonl"
    f.write_text(topic_line("ok-one") + "\n" + bad + "\n", encoding="utf-8")
    with pytest.raises(ValueError) as err:
        block.load_topics(f)
    assert re.search(r"\b2\b", str(err.value))


def test_load_topics_repeated_id_raises(tmp_path):
    f = tmp_path / "topics.jsonl"
    f.write_text(topic_line("dup") + "\n" + topic_line("dup") + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        block.load_topics(f)


def test_load_topics_real_file():
    topics = block.load_topics()
    assert "mtor" in topics and "rapamycin" in topics
    assert "glp1-price" not in topics  # after-m5


# -- CLI coverage with connect -------------------------------------------------------


def coverage_line(out: str) -> str:
    """The coverage line ("topic <slug> covers: ..."; a temp path can hold "cover")."""
    lines = [
        ln.lower()
        for ln in out.splitlines()
        if ln.lower().startswith("topic ") and " covers" in ln.lower()
    ]
    assert lines, f"no coverage line in:\n{out}"
    return lines[-1]


def test_cli_coverage_lists_connect_from_topic_file(cli, env, capsys):
    con = env([connect()], topics=TOPICS)[0].kept[0]
    write_card_file(
        cli.cards_dir / "rapamycin.jsonl",
        [con.model_copy(update={"id": "rapamycin-connect-3"})],
    )
    assert cli(what_and_how_sure(env), "--add") == 0
    line = coverage_line(capsys.readouterr().out)
    assert "connect" in line.split("missing", 1)[0]


def test_cli_coverage_lists_connect_from_kept_cards(cli, env, capsys):
    result, _ = env([*good_drafts(), connect()], topics=TOPICS)
    assert cli(result) == 0
    line = coverage_line(capsys.readouterr().out)
    assert "connect" in line.split("missing", 1)[0]


def test_cli_coverage_never_reports_connect_missing(cli, env, capsys):
    assert cli(what_and_how_sure(env)) == 0
    tail = missing_part(capsys.readouterr().out)
    assert "connect" not in tail


def test_cli_report_line_includes_link_count(cli, env, capsys):
    result, _ = env([*good_drafts(), connect("made-up")], topics=TOPICS)
    assert result.report.dropped_link == 1
    cli(result, "--dry-run")
    assert re.search(r"\blink 1\b", capsys.readouterr().out)


def test_cli_bad_topics_file_prints_one_line_exit_1(cli, capsys):
    error = ValueError("data/topics.jsonl line 3: not a JSON object")
    assert cli(error) == 1
    captured = capsys.readouterr()
    assert str(error) in captured.out + captured.err
    assert list(cli.cards_dir.iterdir()) == []


# ---- Added after the connect review (slugged links_to, empty topic list, early load) -


def test_connect_links_to_is_slugged(env):
    """Topic ids are slugs: "mTOR" and " mTOR " count as "mtor"."""
    other = connect("mTOR", question="Which growth switch is blocked by rapamycin?")
    result, _ = env([connect(" mTOR "), other], topics=TOPICS)
    assert gates(result) == []
    assert [c.id for c in result.kept] == ["rapamycin-connect-1", "rapamycin-connect-2"]


def topic_list_header(prompt: str) -> str:
    """The line just above the first `- <id>: <text>` topic line."""
    lines = prompt.splitlines()
    first = next(i for i, ln in enumerate(lines) if ln.startswith("- mtor:"))
    header = lines[first - 1].strip()
    assert header, "expected a header line right above the topic list"
    return header


@pytest.mark.parametrize(
    "topics",
    [{}, {"rapamycin": TOPICS["rapamycin"]}],
    ids=["no topics", "only own topic"],
)
def test_no_other_topics_prompt_says_write_no_connect_cards(env, topics):
    header = topic_list_header(env(topics=TOPICS)[1][0]["prompt"])
    _, calls = env(topics=topics)
    prompt = calls[0]["prompt"]
    assert header not in prompt
    assert not re.search(r"^- [a-z0-9-]+: ", prompt, re.MULTILINE)
    assert re.search(r"\b(no|not|don't|do not)\b[^.\n]*connect card", prompt.lower())


def test_with_topics_prompt_does_not_say_no_connect_cards(env):
    _, calls = env(topics=TOPICS)
    assert not re.search(r"\bno connect cards?\b", calls[0]["prompt"].lower())


def test_missing_topics_file_raises_before_fetch(env, tmp_path, monkeypatch):
    """topics=None + no topics file: raises before the source is read or fetched."""
    monkeypatch.setattr(block, "TOPICS_FILE", tmp_path / "nope.jsonl")
    fetched: list[str] = []
    ask, calls = fake_ask(good_drafts())

    def fetch(url):
        fetched.append(url)
        return env.fetch(url)

    with pytest.raises(FileNotFoundError):
        block.write_cards(
            "rapamycin",
            SOURCE_ID,
            ask=ask,
            check=fake_check(),
            sources_dir=env.sources_dir,
            root=env.root,  # the document isn't on disk yet, so a read would fetch
            fetch=fetch,
            topics=None,
        )
    assert fetched == []
    assert calls == []


def test_load_topics_without_argument_follows_topics_file(tmp_path, monkeypatch):
    f = tmp_path / "topics.jsonl"
    f.write_text(topic_line("only-one", "Only one") + "\n", encoding="utf-8")
    monkeypatch.setattr(block, "TOPICS_FILE", f)
    assert block.load_topics() == {"only-one": "Only one"}


def test_load_topics_without_argument_missing_topics_file_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(block, "TOPICS_FILE", tmp_path / "nope.jsonl")
    with pytest.raises(FileNotFoundError):
        block.load_topics()


def test_cli_missing_topics_file_prints_one_line_exit_1(tmp_path, monkeypatch, capsys):
    """The real write_cards (not faked): a missing topics file stops the run."""
    from longevity_trainer import cli as cli_module

    cards_dir = tmp_path / "cards"
    cards_dir.mkdir()
    missing = tmp_path / "no-topics.jsonl"
    monkeypatch.setattr(cli_module, "CARDS_DIR", cards_dir)
    monkeypatch.setattr(block, "TOPICS_FILE", missing)
    argv = ["write-cards", "--topic", "rapamycin", "--source", SOURCE_ID]
    assert cli_module.main(argv) == 1
    captured = capsys.readouterr()
    lines = [ln for ln in (captured.out + captured.err).splitlines() if ln.strip()]
    assert len(lines) == 1, lines
    assert "no-topics.jsonl" in lines[0]
    assert list(cards_dir.iterdir()) == []


# ---- Added for the primer (SPEC 2026-11-18, ADR 0010, PROMPT_VERSION 6) ------------

PRIMER_NOTE = "PRIMER-NOTE telomeres shorten with every cell division in people."


def test_primer_text_goes_in_the_prompt_before_the_source(env):
    _, calls = env(primer_text=PRIMER_NOTE)
    prompt = calls[0]["prompt"]
    assert PRIMER_NOTE in prompt
    assert prompt.index(PRIMER_NOTE) < prompt.index(S_WHAT)
    assert re.search(r"primer states", prompt.lower())
    assert "first" in prompt.lower()


def test_no_primer_text_means_no_primer_part(env):
    _, calls = env()
    prompt = calls[0]["prompt"]
    assert PRIMER_NOTE not in prompt
    assert not re.search(r"primer states", prompt.lower())


def test_empty_primer_text_is_the_default(env):
    _, default_calls = env()
    _, empty_calls = env(primer_text="")
    assert default_calls[0]["prompt"] == empty_calls[0]["prompt"]


def test_quote_only_in_the_primer_is_dropped_at_quote(env):
    primer_quote = "Telomeres shorten with every cell division in people."
    q = "What happens to telomeres at cell division?"
    result, _ = env([draft("what", q, quote=primer_quote)], primer_text=primer_quote)
    assert result.kept == []
    assert gates(result) == ["quote"]


# -- CLI primer ----------------------------------------------------------------------

PRIMER_PAGES = [
    "PRIMER-ONE hallmarks of ageing are twelve.",
    "PRIMER-TWO rapamycin inhibits mTOR in the cell.",
    "PRIMER-THREE senescent cells pile up with age.",
]


@pytest.fixture
def primer(monkeypatch):
    """A fake readable primer and a fake tag_cards (first kept card easy, rest hard)."""
    from longevity_trainer import cli as cli_module
    from longevity_trainer.blocks.primer_check import TagResult

    state = type("PrimerFake", (), {})()
    state.calls = []
    state.raises = None
    state.pages = list(PRIMER_PAGES)
    state.loads = 0

    def load_primer(*_a, **_k):
        state.loads += 1
        return list(state.pages)

    def tag_cards(cards, primer_pages, *a, **k):
        state.calls.append((list(cards), list(primer_pages), k))
        if state.raises is not None:
            raise state.raises
        diff = {c.id: ("easy" if i == 0 else "hard") for i, c in enumerate(cards)}
        reasons = {cid: "not in the primer" for cid, d in diff.items() if d == "hard"}
        return TagResult(difficulty=diff, reasons=reasons, model="sonnet")

    monkeypatch.setattr(cli_module, "load_primer", load_primer)
    monkeypatch.setattr(cli_module, "tag_cards", tag_cards)
    return state


def primer_text_of(cli) -> str:
    ((_args, kwargs),) = cli.calls
    return kwargs.get("primer_text")


def output_lines(capsys) -> list[str]:
    captured = capsys.readouterr()
    return [ln for ln in (captured.out + captured.err).splitlines() if ln.strip()]


def test_cli_primer_pages_passes_those_pages_marked(cli, env, primer):
    cli(what_and_how_sure(env), "--primer-pages", "2-3", "--dry-run")
    text = primer_text_of(cli)
    assert re.search(r"\[primer page 2\]\s*" + re.escape(PRIMER_PAGES[1]), text)
    assert re.search(r"\[primer page 3\]\s*" + re.escape(PRIMER_PAGES[2]), text)
    assert text.index("[primer page 2]") < text.index("[primer page 3]")
    assert PRIMER_PAGES[0] not in text and "[primer page 1]" not in text
    assert re.search(re.escape(PRIMER_PAGES[1]) + r"\n\n\[primer page 3\]", text)


def test_cli_primer_pages_single_page(cli, env, primer):
    cli(what_and_how_sure(env), "--primer-pages", "2", "--dry-run")
    text = primer_text_of(cli)
    assert "[primer page 2]" in text and PRIMER_PAGES[1] in text
    assert PRIMER_PAGES[0] not in text and PRIMER_PAGES[2] not in text


def test_cli_without_primer_pages_passes_empty_primer_text(cli, env, primer):
    cli(what_and_how_sure(env), "--dry-run")
    assert primer_text_of(cli) == ""


@pytest.mark.parametrize("flag", ["x", "5-", "0-3", "9-4"])
def test_cli_bad_primer_pages_exits_2_without_calling_write_cards(
    cli, results, primer, flag
):
    with pytest.raises(SystemExit) as exc:
        cli(results["pass"], "--primer-pages", flag)
    assert exc.value.code == 2
    assert cli.calls == []


def test_cli_primer_pages_beyond_the_primer_exit_1_before_claude(
    cli, results, primer, capsys
):
    assert cli(results["pass"], "--primer-pages", "3-5") == 1
    assert cli.calls == []
    assert len(output_lines(capsys)) == 1
    assert list(cli.cards_dir.iterdir()) == []


def test_cli_unreadable_primer_with_primer_pages_exit_1_before_claude(
    cli, results, capsys
):
    """The autouse guard makes load_primer raise FileNotFoundError."""
    assert cli(results["pass"], "--primer-pages", "1-2") == 1
    assert cli.calls == []
    assert len(output_lines(capsys)) == 1
    assert list(cli.cards_dir.iterdir()) == []


def test_cli_kept_cards_are_written_with_their_difficulty(cli, env, primer):
    result = what_and_how_sure(env)
    assert cli(result) == 0
    loaded = load_cards(cli.cards_dir)
    assert [c.id for c in loaded] == [c.id for c in result.kept]
    assert [c.difficulty for c in loaded] == ["easy", "hard"]


def test_cli_tag_cards_gets_the_kept_cards_and_all_primer_pages(cli, env, primer):
    result = what_and_how_sure(env)
    cli(result, "--dry-run")
    ((cards, pages, _k),) = primer.calls
    assert [c.id for c in cards] == [c.id for c in result.kept]
    assert pages == PRIMER_PAGES


def test_cli_tag_cards_uses_the_same_counting_ask(cli, env, primer):
    cli(what_and_how_sure(env), "--dry-run")
    ((_args, wc_kwargs),) = cli.calls
    ((_cards, _pages, tag_kwargs),) = primer.calls
    assert tag_kwargs.get("ask") is not None
    assert tag_kwargs["ask"] is wc_kwargs.get("ask")


def test_cli_prints_tagged_line_before_cost_line(cli, env, primer, capsys):
    assert cli(what_and_how_sure(env)) == 0
    lines = output_lines(capsys)
    tagged = [i for i, ln in enumerate(lines) if "tagged: 1 easy, 1 hard" in ln]
    cost = [i for i, ln in enumerate(lines) if "Claude calls" in ln]
    assert tagged and cost
    assert tagged[0] < cost[0]


def test_cli_dry_run_tags_but_writes_nothing(cli, env, primer, capsys):
    assert cli(what_and_how_sure(env), "--dry-run") == 0
    assert len(primer.calls) == 1
    assert any("tagged: 1 easy, 1 hard" in ln for ln in output_lines(capsys))
    assert list(cli.cards_dir.iterdir()) == []


def test_cli_tag_cards_claude_error_writes_untagged(cli, env, primer, capsys):
    primer.raises = ClaudeError("claude is down")
    result = what_and_how_sure(env)
    assert cli(result) == 0  # exit code unchanged
    lines = output_lines(capsys)
    assert any(
        ln.startswith("not tagged (") and "run tag-levels later" in ln for ln in lines
    )
    assert not any(ln.startswith("tagged:") for ln in lines)
    loaded = load_cards(cli.cards_dir)
    assert [c.id for c in loaded] == [c.id for c in result.kept]
    assert all(c.difficulty is None for c in loaded)


def test_cli_no_primer_no_flag_writes_untagged_exit_0(cli, env, capsys):
    """The autouse guard: no primer file, no --primer-pages."""
    result = what_and_how_sure(env)
    assert cli(result) == 0
    lines = output_lines(capsys)
    assert any(
        ln.startswith("not tagged (can't read the primer: ")
        and "run tag-levels later" in ln
        for ln in lines
    )
    loaded = load_cards(cli.cards_dir)
    assert [c.id for c in loaded] == [c.id for c in result.kept]
    assert all(c.difficulty is None for c in loaded)


def test_cli_not_tagged_line_comes_before_cost_line(cli, env, capsys):
    cli(what_and_how_sure(env), "--dry-run")
    lines = output_lines(capsys)
    nt = [i for i, ln in enumerate(lines) if ln.startswith("not tagged (")]
    cost = [i for i, ln in enumerate(lines) if "Claude calls" in ln]
    assert nt and cost and nt[0] < cost[0]


def test_cli_run_that_keeps_nothing_does_not_tag(cli, results, primer, capsys):
    assert cli(results["empty"]) == 1
    assert primer.calls == []
    lines = output_lines(capsys)
    assert not any(ln.startswith(("tagged:", "not tagged")) for ln in lines)


def test_cli_primer_text_is_never_printed_or_written(cli, env, primer, capsys):
    assert cli(what_and_how_sure(env), "--primer-pages", "1-3") == 0
    captured = capsys.readouterr()
    shown = captured.out + captured.err
    written = (cli.cards_dir / "rapamycin.jsonl").read_text(encoding="utf-8")
    for page in PRIMER_PAGES:
        assert page not in shown
        assert page not in written


# ---- Added after the primer review (read only when needed, blank pages, bar) -------


def test_whitespace_only_primer_text_means_no_primer_part(env):
    _, default_calls = env()
    _, blank_calls = env(primer_text="   \n  ")
    assert blank_calls[0]["prompt"] == default_calls[0]["prompt"]


def test_system_prompt_says_never_to_quote_the_primer(env):
    _, calls = env(primer_text=PRIMER_NOTE)
    system = calls[0]["system"].lower()
    assert re.search(
        r"(never|not|don't)[^.\n]*quot[^.\n]*primer"
        r"|primer[^.\n]*(never|not|don't)[^.\n]*quot",
        system,
    )


def test_cli_chosen_primer_pages_with_no_text_exit_1(cli, results, primer, capsys):
    primer.pages = [PRIMER_PAGES[0], "   ", "\n"]
    assert cli(results["pass"], "--primer-pages", "2-3") == 1
    assert cli.calls == []
    assert len(output_lines(capsys)) == 1


def test_cli_primer_with_every_page_blank_exit_1(cli, results, primer, capsys):
    primer.pages = ["", "  ", "\n"]
    assert cli(results["pass"], "--primer-pages", "1-3") == 1
    assert cli.calls == []
    assert len(output_lines(capsys)) == 1


def test_cli_existing_file_refuses_without_reading_the_primer(cli, results, primer):
    (cli.cards_dir / "rapamycin.jsonl").write_text("old\n", encoding="utf-8")
    assert cli(results["pass"], "--primer-pages", "1-2") == 1
    assert cli.calls == []
    assert primer.loads == 0


def test_cli_run_that_misses_the_bar_does_not_tag(cli, results, primer, capsys):
    assert results["fail"].kept  # cards kept, bar missed
    assert cli(results["fail"]) == 1
    assert primer.calls == []
    lines = output_lines(capsys)
    assert not any(ln.startswith(("tagged:", "not tagged")) for ln in lines)


def test_cli_blank_primer_without_flag_is_not_tagged(cli, env, primer, capsys):
    primer.pages = ["", "  "]
    result = what_and_how_sure(env)
    assert cli(result) == 0
    assert primer.calls == []
    lines = output_lines(capsys)
    assert any(ln.startswith("not tagged (can't read the primer: ") for ln in lines)
    assert all(c.difficulty is None for c in load_cards(cli.cards_dir))


def test_cli_claude_error_prints_only_text_before_colon(cli, env, primer, capsys):
    primer.raises = ClaudeError("bad reply: PRIMER-SECRET words from the primer")
    assert cli(what_and_how_sure(env)) == 0
    captured = capsys.readouterr()
    shown = captured.out + captured.err
    assert any(
        ln.startswith("not tagged (bad reply): ") and "run tag-levels later" in ln
        for ln in shown.splitlines()
    )
    assert "PRIMER-SECRET" not in shown


# ---- Added for `only_asks`, the ask gate and v7 (SPEC 2026-11-18) ------------------


def only_asks_drafts() -> list[dict]:
    """A what, a how and a catch draft, all with real quotes."""
    return [
        draft("what", "What does rapamycin inhibit in the cell?", quote=S_WHAT),
        draft("how", "How does rapamycin slow cell growth?", quote=S_HOW),
        draft("catch", "What side effect can rapamycin cause?", quote=S_CATCH),
    ]


def new_lines(prompt: str, baseline: str) -> list[str]:
    """Lines in `prompt` that aren't in `baseline` (lower case)."""
    old = set(baseline.lower().splitlines())
    return [ln for ln in prompt.lower().splitlines() if ln not in old]


def test_block_spec_lists_only_asks_input():
    assert "only_asks" in block.BLOCK_SPEC.inputs


def test_only_asks_prompt_says_write_only_those_asks(env):
    _, base = env(only_asks_drafts())
    _, calls = env(only_asks_drafts(), only_asks=["how"])
    added = new_lines(calls[0]["prompt"], base[0]["prompt"])
    assert any("only" in ln and "how" in ln for ln in added), added


def test_only_asks_two_asks_prompt_names_both(env):
    _, base = env(only_asks_drafts())
    _, calls = env(only_asks_drafts(), only_asks=["how", "catch"])
    added = " ".join(new_lines(calls[0]["prompt"], base[0]["prompt"]))
    assert "only" in added and "how" in added and "catch" in added


def test_only_asks_drops_other_asks_at_ask_gate(env):
    check = fake_check()
    result, _ = env(only_asks_drafts(), only_asks=["how"], check=check)
    assert [c.question for c in result.kept] == ["How does rapamycin slow cell growth?"]
    assert gates(result) == ["ask", "ask"]
    assert result.drops[0].reason == "asked for only how"
    assert result.report.dropped_ask == 2
    assert [c.question for c in check.calls] == ["How does rapamycin slow cell growth?"]
    assert result.report.passed is True
    assert_counts_add_up(result.report, result)


def test_ask_gate_comes_before_quote_gate(env):
    """An off-ask draft with an invented quote counts in dropped_ask, not the quote bar."""
    fake = "Rapamycin doubled the lifespan of every human volunteer tested."
    drafts = [
        draft("what", "What is invented about rapamycin here?", quote=fake),
        draft("how", "How does rapamycin slow cell growth?", quote=S_HOW),
    ]
    result, _ = env(drafts, only_asks=["how"])
    assert gates(result) == ["ask"]
    assert (result.report.dropped_ask, result.report.dropped_quote) == (1, 0)
    assert result.report.passed is True
    assert_counts_add_up(result.report, result)


def test_shape_gate_comes_before_ask_gate(env):
    drafts = [draft("what", question="Short"), only_asks_drafts()[1]]
    result, _ = env(drafts, only_asks=["how"])
    assert gates(result) == ["shape"]
    assert result.report.dropped_ask == 0


def test_only_asks_two_asks_keeps_both(env):
    result, _ = env(only_asks_drafts(), only_asks=["how", "catch"])
    assert sorted(c.id for c in result.kept) == ["rapamycin-catch-1", "rapamycin-how-1"]
    assert gates(result) == ["ask"]
    assert result.report.asks_kept == ["catch", "how"]
    assert_counts_add_up(result.report, result)


def test_only_asks_with_primer_says_only_primer_facts(env):
    _, calls = env(only_asks_drafts(), only_asks=["how"], primer_text=PRIMER_NOTE)
    prompt = calls[0]["prompt"].lower()
    assert PRIMER_NOTE.lower() in prompt
    lines = [ln for ln in prompt.splitlines() if "primer states" in ln]
    assert any("only" in ln for ln in lines), lines
    assert "other facts" not in prompt


def test_only_asks_none_adds_no_line_and_drops_nothing(env):
    _, base = env(only_asks_drafts())
    result, calls = env(only_asks_drafts(), only_asks=None)
    assert calls[0]["prompt"] == base[0]["prompt"]
    assert gates(result) == []
    assert result.report.dropped_ask == 0


def test_dropped_ask_defaults_to_0_and_is_in_model_dump(env):
    result, _ = env()
    assert result.report.dropped_ask == 0
    assert result.report.model_dump()["dropped_ask"] == 0


@pytest.mark.parametrize("only_asks", [[], ["why"], ["how", "why"]])
def test_bad_only_asks_raises_before_claude(env, only_asks):
    ask, calls = fake_ask(only_asks_drafts())
    with pytest.raises(ValueError):
        env(ask=ask, only_asks=only_asks)
    assert calls == []


def test_drop_accepts_ask_gate():
    d = block.Drop(question="What is it?", gate="ask", reason="asked for only how")
    assert d.gate == "ask"


def test_system_prompt_has_learners_level_rule(env):
    _, calls = env()
    system = calls[0]["system"].lower()
    assert "equation" in system
    assert re.search(r"\bfl(y|ies)\b", system)
    assert "worm" in system and "yeast" in system


# -- CLI `--ask` ---------------------------------------------------------------------


def ask_result(env):
    """A passing result with one draft dropped at the ask gate."""
    result, _ = env(only_asks_drafts()[:2], only_asks=["how"])
    assert result.report.dropped_ask == 1 and result.report.passed
    return result


def test_cli_ask_flags_pass_only_asks(cli, results):
    cli(results["pass"], "--ask", "how", "--ask", "catch", "--dry-run")
    ((_args, kwargs),) = cli.calls
    assert kwargs["only_asks"] == ["how", "catch"]


def test_cli_ask_flags_are_passed_in_asks_order(cli, results):
    cli(results["pass"], "--ask", "catch", "--ask", "how", "--dry-run")
    ((_args, kwargs),) = cli.calls
    assert kwargs["only_asks"] == ["how", "catch"]


def test_cli_repeated_ask_passed_once(cli, results):
    cli(results["pass"], "--ask", "how", "--ask", "how", "--dry-run")
    ((_args, kwargs),) = cli.calls
    assert kwargs["only_asks"] == ["how"]


def test_cli_without_ask_passes_none(cli, results):
    cli(results["pass"], "--dry-run")
    ((_args, kwargs),) = cli.calls
    assert kwargs.get("only_asks") is None


def test_cli_bad_ask_exits_2_without_calling_write_cards(cli, results):
    with pytest.raises(SystemExit) as exc:
        cli(results["pass"], "--ask", "why", "--dry-run")
    assert exc.value.code == 2
    assert cli.calls == []


def test_cli_report_line_has_ask_count_with_flag(cli, env, capsys):
    cli(ask_result(env), "--ask", "how", "--dry-run")
    assert re.search(r"\bchecker \d+, ask 1\b", capsys.readouterr().out)


def test_cli_report_line_has_no_ask_count_without_flag(cli, env, capsys):
    cli(what_and_how_sure(env), "--dry-run")
    out = capsys.readouterr().out
    assert re.search(r"\bchecker \d+", out)
    assert not re.search(r"\bchecker \d+, ask \d+", out)


# ---- Added after the only_asks review (bar denominator, connect, gap-fill CLI) -----

NO_CONNECT = re.compile(r"\b(no|not|don't|do not)\b[^.\n]*connect card")


def test_ask_reason_lists_asks_in_asks_order(env):
    result, _ = env(only_asks_drafts()[:1], only_asks=["catch", "how"])
    assert [d.reason for d in result.drops] == ["asked for only how, catch"]


def test_repeated_only_ask_counts_once(env):
    result, _ = env(only_asks_drafts()[:2], only_asks=["how", "how"])
    assert [d.reason for d in result.drops] == ["asked for only how"]
    assert len(result.kept) == 1


def test_bar_off_ask_drafts_do_not_pad_it_spec_case(env):
    """8 off-ask + 2 invented-quote how drafts: 2 of 2 reaching the quote gate missing."""
    fake = "Rapamycin doubled the lifespan of every human volunteer tested."
    off = [draft("what", f"What else is true of rapamycin, no {i}?") for i in range(8)]
    bad = [
        draft("how", f"How does it work in people, no {i}?", quote=fake)
        for i in range(2)
    ]
    result, _ = env([*off, *bad], only_asks=["how"], n=10)
    r = result.report
    assert (r.drafted, r.dropped_ask, r.dropped_quote) == (10, 8, 2)
    assert r.passed is False


def test_bar_off_ask_drafts_not_in_the_denominator(env):
    """7 off-ask, 1 invented, 2 good: 1 of 3 missing fails (it would pass over 10)."""
    fake = "Rapamycin doubled the lifespan of every human volunteer tested."
    off = [draft("what", f"What else is true of rapamycin, no {i}?") for i in range(7)]
    drafts = [
        *off,
        draft("how", "How does it work in people, really?", quote=fake),
        draft("how", "How does rapamycin slow cell growth?", quote=S_HOW),
        draft("how", "How does rapamycin act on mTORC1 signalling?", quote=S_HOW),
    ]
    result, _ = env(drafts, only_asks=["how"], n=10)
    r = result.report
    assert (r.dropped_ask, r.dropped_quote, r.kept) == (7, 1, 2)
    assert r.passed is False


def test_bar_shape_drops_not_in_the_denominator(env):
    """3 shape, 1 invented, 1 good: 1 of 2 reaching the quote gate missing fails."""
    fake = "Rapamycin doubled the lifespan of every human volunteer tested."
    drafts = [
        draft("what", question="Short"),
        draft("what", question="Tiny"),
        draft("what", question="Brief"),
        draft("how", "How does it work in people, really?", quote=fake),
        draft("how", "How does rapamycin slow cell growth?", quote=S_HOW),
    ]
    result, _ = env(drafts, n=5)
    r = result.report
    assert (r.dropped_shape, r.dropped_quote, r.kept) == (3, 1, 1)
    assert r.passed is False


def test_only_asks_without_connect_sends_no_topic_list(env):
    _, calls = env(only_asks_drafts(), only_asks=["how"], topics=TOPICS)
    prompt = calls[0]["prompt"]
    assert not re.search(r"^- [a-z0-9-]+: ", prompt, re.MULTILINE)
    assert NO_CONNECT.search(prompt.lower())


def test_only_asks_with_connect_sends_the_topic_list(env):
    _, calls = env([connect()], only_asks=["connect"], topics=TOPICS)
    prompt = calls[0]["prompt"]
    assert "- mtor: " in prompt
    assert not re.search(r"\bno connect cards?\b", prompt.lower())


def test_only_asks_line_says_it_overrides_the_cover_rules(env):
    _, base = env(only_asks_drafts())
    _, calls = env(only_asks_drafts(), only_asks=["how"])
    added = " ".join(new_lines(calls[0]["prompt"], base[0]["prompt"]))
    assert "overrid" in added


@pytest.mark.parametrize(
    "topics", [{}, {"rapamycin": TOPICS["rapamycin"]}], ids=["none", "only own"]
)
def test_only_connect_with_no_topic_to_link_raises_before_claude(env, topics):
    ask, calls = fake_ask([connect()])
    with pytest.raises(ValueError):
        env(ask=ask, only_asks=["connect"], topics=topics)
    assert calls == []


def test_system_prompt_level_is_a_well_read_non_specialist(env):
    _, calls = env()
    assert "well-read non-specialist" in calls[0]["system"].lower()


# -- CLI gap fill --------------------------------------------------------------------


def test_cli_ask_with_replace_exits_2_without_calling_write_cards(cli, results):
    with pytest.raises(SystemExit) as exc:
        cli(results["pass"], "--ask", "how", "--replace")
    assert exc.value.code == 2
    assert cli.calls == []


def test_cli_gap_fill_with_primer_writes_only_easy_cards(cli, env, primer, capsys):
    result = what_and_how_sure(env)  # the fake tags the first easy, the rest hard
    easy, hard = result.kept
    assert cli(result, "--ask", "how", "--primer-pages", "2-3") == 0
    loaded = load_cards(cli.cards_dir)
    assert [c.id for c in loaded] == [easy.id]
    assert loaded[0].difficulty == "easy"
    lines = output_lines(capsys)
    assert f"not kept (hard): {hard.question}" in [ln.strip() for ln in lines]
    assert not any(easy.question in ln and "not kept" in ln for ln in lines)


def test_cli_gap_fill_coverage_counts_only_written_cards(cli, env, primer, capsys):
    """The hard how_sure card isn't written, so how_sure is still missing."""
    assert cli(what_and_how_sure(env), "--ask", "how", "--primer-pages", "2-3") == 0
    out = "\n".join(output_lines(capsys))
    assert re.search(r"how[_ -]sure", missing_part(out))


def test_cli_gap_fill_tagging_failure_writes_nothing(cli, env, primer, capsys):
    primer.raises = ClaudeError("claude is down")
    assert cli(what_and_how_sure(env), "--ask", "how", "--primer-pages", "2-3") == 0
    assert list(cli.cards_dir.iterdir()) == []
    lines = output_lines(capsys)
    assert "nothing written: a gap fill keeps only easy cards" in lines
    assert any(ln.startswith("not tagged (") for ln in lines)


def test_cli_primer_pages_without_ask_still_writes_hard_cards(cli, env, primer, capsys):
    result = what_and_how_sure(env)
    assert cli(result, "--primer-pages", "2-3") == 0
    loaded = load_cards(cli.cards_dir)
    assert [c.difficulty for c in loaded] == ["easy", "hard"]
    assert not any(ln.startswith("not kept (hard)") for ln in output_lines(capsys))
