"""Tests for the card_writer block: contract (ID card + SPEC) and behaviour (from SPEC.md).

Test-first, black-box: the real Claude never runs (a fake `ask`), the card checker
is a fake `check`, and sources are tiny html/PDF files pinned in a temp folder.
"""

import hashlib
import json
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
        "sources_dir",
        "root",
        "fetch",
    }
    assert set(block.BLOCK_SPEC.outputs) == {
        "write_cards",
        "Draft",
        "Drop",
        "WriterReport",
        "PROMPT_VERSION",
        "slug",
    }


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
            **kwargs,
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
        + report.dropped_quote
        + report.dropped_repeat
        + report.dropped_checker
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


def test_fails_when_how_sure_missing(env):
    drafts = [d for d in good_drafts() if d["asks"] != "how_sure"]
    result, _ = env(drafts)
    assert "how_sure" not in result.report.asks_kept
    assert result.report.passed is False


def test_fails_when_3_of_10_quotes_missing(env):
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


def test_fails_when_fewer_than_half_kept(env):
    bad = [
        draft("what", f"What breaks the checker, number {i}?", quote=S_WHAT)
        for i in range(5)
    ]
    result, _ = env([*good_drafts()[:3], *bad], check=fake_check({"breaks": 3}))
    r = result.report
    assert (r.drafted, r.kept) == (8, 3)
    assert r.passed is False


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
    failing, _ = env([d for d in good_drafts() if d["asks"] != "how_sure"])
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


def test_cli_existing_file_without_replace_exits_1_before_drafting(cli, results):
    out = cli.cards_dir / "rapamycin.jsonl"
    out.write_text("old\n", encoding="utf-8")
    assert cli(results["pass"]) == 1
    assert cli.calls == []
    assert out.read_text(encoding="utf-8") == "old\n"


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


def test_prompt_version_is_3():
    assert block.PROMPT_VERSION == "3"


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
    out.write_text("old\n", encoding="utf-8")
    cli(results["pass"], "--dry-run")
    assert len(cli.calls) == 1
    assert out.read_text(encoding="utf-8") == "old\n"
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
