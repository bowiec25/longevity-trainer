"""Tests for the primer_check block: contract (ID card + SPEC) and behaviour (from SPEC.md).

Test-first, black-box: the real Claude never runs (a fake `ask`), the primer is a few
page strings written here (never the real PDF), and the CLI gets a fake `tag_cards`
and `load_primer` and a temporary CARDS_DIR. Names are reached through the module
(`block.tag_cards`) so each test fails on its own until the code exists.
"""

import json
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import longevity_trainer.blocks.primer_check as block
from longevity_trainer.blocks.card_bank import LongevityCard, load_cards
from quizkit.blocks.base import missing_spec_sections, spec_section
from quizkit.blocks.receipts import to_key
from quizkit.claude import ClaudeError, ClaudeReply

SPEC_MD = Path(block.__file__).parent / "SPEC.md"


# -- Contract ------------------------------------------------------------------------


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "primer_check"
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
    inputs = set(block.BLOCK_SPEC.inputs)
    outputs = set(block.BLOCK_SPEC.outputs)
    assert {"cards", "primer_pages", "ask", "model", "path"} <= inputs
    assert {"PRIMER_FILE", "load_primer", "tag_cards", "TagResult"} <= {
        o.split("(")[0] for o in outputs
    }


# -- Helpers -------------------------------------------------------------------------

PAGE_1 = "Ageing is the gradual loss of function over time. Many systems decline."
PAGE_2 = (
    "Telomeres shorten each time a cell divides. "
    "Short telomeres stop cells from dividing. Senescent cells pile up with age."
)
PAGE_3 = (
    "Rapamycin inhibits mTOR, a growth pathway that senses nutrients. "
    "It extends lifespan in mice."
)
PAGES = [PAGE_1, PAGE_2, PAGE_3]
# A real primer passage whose key is well over MIN_QUOTE_KEY (30) characters.
RAPA_QUOTE = "Rapamycin inhibits mTOR, a growth pathway that senses nutrients."


def make_card(id="hm-telomeres-name", topic="hallmarks: telomere attrition", **extra):
    data = {
        "id": id,
        "kind": "name",
        "topic": topic,
        "question": f"Which hallmark is card {id} about, exactly?",
        "answers": [f"answer for {id}", "another answer"],
        "receipt": {
            "source": "hallmarks-of-aging-2023",
            "quote": "telomeres undergo a substantial shortening",
            "page": 9,
        },
    }
    data.update(extra)
    return LongevityCard(**data)


def verdict(card_id, in_primer=True, primer_quote=""):
    return {"card_id": card_id, "in_primer": in_primer, "primer_quote": primer_quote}


def reply(text: str) -> ClaudeReply:
    return ClaudeReply(
        text=text,
        model="claude-sonnet-test",
        input_tokens=10,
        output_tokens=5,
        cost_usd=0.001,
    )


def fake_ask(verdicts=None, text=None, raises=None):
    """An `ask` that records each call and returns {"verdicts": verdicts}."""
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
        body = text if text is not None else json.dumps({"verdicts": verdicts or []})
        return reply(body)

    return ask, calls


def tag(cards, verdicts, **kwargs):
    ask, calls = fake_ask(verdicts)
    return block.tag_cards(cards, PAGES, ask=ask, **kwargs), calls


# -- tag_cards: the rule -------------------------------------------------------------


def test_quote_found_on_page_2_is_easy():
    card = make_card("a")
    result, _ = tag(
        [card], [verdict("a", True, "Telomeres shorten each time a cell divides.")]
    )
    assert result.difficulty == {"a": "easy"}
    assert result.reasons == {}


def test_quote_found_despite_case_and_punctuation_is_easy():
    """The quote is matched by `to_key`, so case and punctuation don't matter."""
    card = make_card("a")
    quote = "telomeres shorten, each time a cell divides"
    result, _ = tag([card], [verdict("a", True, quote)])
    assert result.difficulty["a"] == "easy"


def test_two_consecutive_sentences_quote_is_easy():
    card = make_card("a")
    quote = "Telomeres shorten each time a cell divides. Short telomeres stop cells from dividing."
    result, _ = tag([card], [verdict("a", True, quote)])
    assert result.difficulty["a"] == "easy"


def test_min_quote_key_is_30():
    assert block.MIN_QUOTE_KEY == 30


def test_short_real_quote_is_hard_quote_not_found():
    """A one-word quote is in any primer somewhere: it proves nothing."""
    card = make_card("a")
    result, _ = tag([card], [verdict("a", True, "telomeres")])
    assert result.difficulty == {"a": "hard"}
    assert result.reasons == {"a": "primer quote not found"}


def test_real_quote_with_29_key_characters_is_hard():
    quote = "Telomeres shorten each time a cell"
    assert len(to_key(quote)) == 29
    result, _ = tag([make_card("a")], [verdict("a", True, quote)])
    assert result.difficulty == {"a": "hard"}
    assert result.reasons == {"a": "primer quote not found"}


def test_real_quote_with_exactly_30_key_characters_is_easy():
    quote = "Telomeres shorten each time a cell d"
    assert len(to_key(quote)) == 30
    result, _ = tag([make_card("a")], [verdict("a", True, quote)])
    assert result.difficulty == {"a": "easy"}
    assert result.reasons == {}


def test_in_primer_with_made_up_quote_is_hard_quote_not_found():
    card = make_card("a")
    result, _ = tag(
        [card], [verdict("a", True, "Telomeres grow longer with exercise.")]
    )
    assert result.difficulty == {"a": "hard"}
    assert result.reasons == {"a": "primer quote not found"}


def test_in_primer_with_empty_quote_is_hard_quote_not_found():
    card = make_card("a")
    result, _ = tag([card], [verdict("a", True, "")])
    assert result.difficulty["a"] == "hard"
    assert result.reasons["a"] == "primer quote not found"


def test_not_in_primer_is_hard():
    card = make_card("a")
    result, _ = tag([card], [verdict("a", False, "")])
    assert result.difficulty == {"a": "hard"}
    assert result.reasons == {"a": "not in the primer"}


def test_not_in_primer_is_hard_even_with_a_real_quote():
    card = make_card("a")
    result, _ = tag([card], [verdict("a", False, RAPA_QUOTE)])
    assert result.difficulty["a"] == "hard"
    assert result.reasons["a"] == "not in the primer"


def test_card_missing_from_reply_is_hard_no_verdict():
    a, b = make_card("a"), make_card("b")
    result, _ = tag([a, b], [verdict("a", True, RAPA_QUOTE)])
    assert result.difficulty == {"a": "easy", "b": "hard"}
    assert result.reasons == {"b": "no verdict"}


def test_reply_ids_not_sent_are_ignored():
    card = make_card("a")
    verdicts = [
        verdict("ghost", True, RAPA_QUOTE),
        verdict("a", False, ""),
    ]
    result, _ = tag([card], verdicts)
    assert result.difficulty == {"a": "hard"}
    assert "ghost" not in result.reasons


def test_repeated_id_first_entry_counts():
    card = make_card("a")
    verdicts = [
        verdict("a", True, RAPA_QUOTE),
        verdict("a", False, ""),
    ]
    result, _ = tag([card], verdicts)
    assert result.difficulty == {"a": "easy"}


def test_repeated_id_first_entry_counts_when_it_is_hard():
    card = make_card("a")
    verdicts = [
        verdict("a", False, ""),
        verdict("a", True, RAPA_QUOTE),
    ]
    result, _ = tag([card], verdicts)
    assert result.difficulty == {"a": "hard"}
    assert result.reasons == {"a": "not in the primer"}


def test_difficulty_has_exactly_the_ids_sent_and_reasons_only_for_hard():
    cards = [make_card(i) for i in ["a", "b", "c", "d"]]
    verdicts = [
        verdict("a", True, RAPA_QUOTE),
        verdict("b", True, "A made up sentence that appears nowhere in the primer."),
        verdict("c", False, ""),
        verdict("zzz", True, RAPA_QUOTE),
    ]
    result, _ = tag(cards, verdicts)
    assert set(result.difficulty) == {"a", "b", "c", "d"}
    assert set(result.difficulty.values()) <= {"easy", "hard"}
    hard = {k for k, v in result.difficulty.items() if v == "hard"}
    assert set(result.reasons) == hard == {"b", "c", "d"}
    assert result.reasons == {
        "b": "primer quote not found",
        "c": "not in the primer",
        "d": "no verdict",
    }


def test_one_claude_call_for_all_the_cards():
    cards = [make_card(i) for i in ["a", "b", "c"]]
    _, calls = tag(cards, [])
    assert len(calls) == 1


def test_no_cards_gives_empty_result_and_no_call():
    ask, calls = fake_ask([])
    result = block.tag_cards([], PAGES, ask=ask)
    assert isinstance(result, block.TagResult)
    assert result.difficulty == {}
    assert result.reasons == {}
    assert calls == []


def test_result_reports_model_and_prompt_version():
    result, _ = tag([make_card("a")], [], model="haiku")
    assert result.model == "haiku"
    assert result.prompt_version == block.PROMPT_VERSION


def test_prompt_version_is_1():
    assert block.PROMPT_VERSION == "1"


# -- Prompt --------------------------------------------------------------------------


def test_system_prompt_says_same_claim_not_same_topic():
    _, (call,) = tag([make_card("a")], [])
    system = call["system"].lower()
    assert "same claim" in system
    assert "topic" in system


def test_system_prompt_says_quote_exactly():
    _, (call,) = tag([make_card("a")], [])
    system = call["system"].lower()
    assert "exactly" in system
    assert "paraphrase" in system


def test_system_prompt_says_unsure_means_false():
    _, (call,) = tag([make_card("a")], [])
    system = call["system"].lower()
    assert "unsure" in system
    assert "false" in system


def test_user_prompt_has_each_cards_id_question_and_answers():
    cards = [make_card("a"), make_card("b", answers=["mTOR", "target of rapamycin"])]
    _, (call,) = tag(cards, [])
    prompt = call["prompt"]
    for card in cards:
        assert card.id in prompt
        assert card.question in prompt
        for answer in card.answers:
            assert answer in prompt


def test_user_prompt_has_the_primer_pages_marked():
    _, (call,) = tag([make_card("a")], [])
    prompt = call["prompt"]
    for number, page in enumerate(PAGES, start=1):
        assert f"[page {number}]" in prompt
        assert page in prompt
    assert prompt.index("[page 1]") < prompt.index(PAGE_1) < prompt.index("[page 2]")
    assert prompt.index("[page 2]") < prompt.index(PAGE_2) < prompt.index("[page 3]")


def test_reply_schema_is_passed():
    _, (call,) = tag([make_card("a")], [])
    schema = call["json_schema"]
    assert isinstance(schema, dict)
    text = json.dumps(schema)
    for key in ["verdicts", "card_id", "in_primer", "primer_quote"]:
        assert key in text


def test_default_model_is_sonnet():
    result, (call,) = tag([make_card("a")], [])
    assert call["model"] == "sonnet"
    assert result.model == "sonnet"


def test_chosen_model_is_passed():
    _, (call,) = tag([make_card("a")], [], model="haiku")
    assert call["model"] == "haiku"


@pytest.mark.parametrize(
    "text",
    [
        "not json at all",
        json.dumps({"cards": []}),
        json.dumps({"verdicts": [{"card_id": "a"}]}),
        json.dumps(
            {"verdicts": [{"card_id": "a", "in_primer": "maybe", "primer_quote": ""}]}
        ),
        json.dumps(["a", "b"]),
    ],
    ids=["not-json", "wrong-key", "missing-fields", "bad-bool", "not-an-object"],
)
def test_bad_reply_raises_claude_error(text):
    ask, _ = fake_ask(text=text)
    with pytest.raises(ClaudeError, match="bad reply"):
        block.tag_cards([make_card("a")], PAGES, ask=ask)


def test_claude_error_from_ask_propagates():
    ask, _ = fake_ask(raises=ClaudeError("claude is not installed"))
    with pytest.raises(ClaudeError):
        block.tag_cards([make_card("a")], PAGES, ask=ask)


# -- load_primer ---------------------------------------------------------------------


def make_text_pdf(path: Path, texts: list[str]) -> Path:
    """A tiny PDF with one line of Helvetica text per page (as in test_receipts)."""
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


def test_primer_file_is_the_users_primer_outside_the_repo():
    expected = (
        Path.home()
        / "Desktop"
        / "Longevity_Platform_Blueprint"
        / "1_DOCS"
        / "longevity_trends_primer.pdf"
    )
    assert block.PRIMER_FILE == expected


def test_load_primer_reads_the_given_pdf_one_string_per_page(tmp_path):
    pdf = make_text_pdf(
        tmp_path / "primer.pdf", ["Rapamycin inhibits mTOR.", "Telomeres shorten."]
    )
    pages = block.load_primer(pdf)
    assert len(pages) == 2
    assert "Rapamycin inhibits mTOR" in pages[0]
    assert "Telomeres shorten" in pages[1]


def test_load_primer_without_argument_follows_patched_primer_file(
    tmp_path, monkeypatch
):
    pdf = make_text_pdf(tmp_path / "mine.pdf", ["Autophagy recycles cell parts."])
    monkeypatch.setattr(block, "PRIMER_FILE", pdf)
    pages = block.load_primer()
    assert len(pages) == 1
    assert "Autophagy recycles cell parts" in pages[0]


def test_load_primer_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        block.load_primer(tmp_path / "nope.pdf")


def test_load_primer_default_missing_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(block, "PRIMER_FILE", tmp_path / "gone.pdf")
    with pytest.raises(FileNotFoundError):
        block.load_primer()


# -- CLI: `longevity tag-levels` -----------------------------------------------------

# hallmarks.jsonl: two hallmark cards. drugs.jsonl: two drug cards and one hallmark
# card, so grouping is by topic group (study.group_of), not by file.
HM = ["hm-1", "hm-2"]
DR = ["dr-1", "dr-2"]
HM_IN_DRUGS_FILE = "hm-3"


def bank_cards(levels: dict | None = None) -> dict[str, list[LongevityCard]]:
    """{file name: cards}; `levels` sets a starting difficulty per id."""
    levels = levels or {}

    def c(id, topic):
        extra = {"difficulty": levels[id]} if id in levels else {}
        return make_card(id, topic=topic, **extra)

    return {
        "hallmarks.jsonl": [
            c("hm-1", "hallmarks: telomere attrition"),
            c("hm-2", "hallmarks: dysbiosis"),
        ],
        "drugs.jsonl": [
            c("dr-1", "drugs: rapamycin"),
            c(HM_IN_DRUGS_FILE, "hallmarks: stem cell exhaustion"),
            c("dr-2", "drugs: metformin"),
        ],
    }


def write_bank(cards_dir: Path, files: dict[str, list[LongevityCard]]) -> None:
    for name, cards in files.items():
        text = "".join(card.model_dump_json() + "\n" for card in cards)
        (cards_dir / name).write_text(text, encoding="utf-8")


def file_lines(path: Path) -> list[str]:
    return [
        line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


@pytest.fixture
def cli(tmp_path, monkeypatch):
    """Run `tag-levels` with a fake tag_cards / load_primer and a temp CARDS_DIR.

    `run(*args, levels=..., raises_for=..., during=...)`:
    - `levels`: {id: "easy" | "hard"} the fake tags (default easy)
    - `raises_for`: a group name whose call raises ClaudeError
    - `during`: called with the group name inside each tag_cards call (to edit files)
    - `primer_error`: an exception the fake load_primer raises
    - `pages`: the pages the fake load_primer returns (default PAGES)
    """
    from longevity_trainer import cli as cli_module

    cards_dir = tmp_path / "cards"
    cards_dir.mkdir()
    monkeypatch.setattr(cli_module, "CARDS_DIR", cards_dir)
    calls: list[dict] = []
    primer_calls: list = []

    def run(
        *args,
        levels=None,
        raises_for=None,
        during=None,
        primer_error=None,
        pages=None,
    ):
        levels = levels or {}

        def fake_load_primer(*a, **k):
            primer_calls.append((a, k))
            if primer_error is not None:
                raise primer_error
            return list(PAGES if pages is None else pages)

        def fake_tag_cards(*a, **k):
            cards = a[0] if a else k["cards"]
            pages = a[1] if len(a) > 1 else k.get("primer_pages")
            groups = {c.topic.split(":", 1)[0].strip() for c in cards}
            calls.append(
                {"ids": [c.id for c in cards], "pages": pages, "groups": groups}
            )
            group = next(iter(groups))
            if during is not None:
                during(group)
            if group == raises_for:
                raise ClaudeError(f"claude broke on {group}")
            difficulty = {c.id: levels.get(c.id, "easy") for c in cards}
            reasons = {
                i: "not in the primer" for i, d in difficulty.items() if d == "hard"
            }
            return block.TagResult(
                difficulty=difficulty,
                reasons=reasons,
                model="sonnet",
                prompt_version=block.PROMPT_VERSION,
            )

        monkeypatch.setattr(cli_module, "load_primer", fake_load_primer)
        monkeypatch.setattr(cli_module, "tag_cards", fake_tag_cards)
        return cli_module.main(["tag-levels", *args])

    run.cards_dir = cards_dir
    run.calls = calls
    run.primer_calls = primer_calls
    return run


def by_id(cards_dir: Path) -> dict[str, LongevityCard]:
    return {c.id: c for c in load_cards(cards_dir)}


# output and grouping


def test_cli_one_call_per_topic_group(cli):
    write_bank(cli.cards_dir, bank_cards())
    assert cli("--dry-run") == 0
    assert len(cli.calls) == 2
    sent = {frozenset(call["groups"]): set(call["ids"]) for call in cli.calls}
    assert sent == {
        frozenset({"hallmarks"}): {*HM, HM_IN_DRUGS_FILE},
        frozenset({"drugs"}): set(DR),
    }


def test_cli_passes_the_primer_pages_to_tag_cards(cli):
    write_bank(cli.cards_dir, bank_cards())
    cli("--dry-run")
    assert all(call["pages"] == PAGES for call in cli.calls)


def test_cli_primer_flag_is_passed_to_load_primer(cli, tmp_path):
    write_bank(cli.cards_dir, bank_cards())
    mine = tmp_path / "my-primer.pdf"
    cli("--dry-run", "--primer", str(mine))
    ((a, k),) = cli.primer_calls
    given = list(a) + list(k.values())
    assert [Path(str(x)) for x in given] == [mine]


def test_cli_cards_with_difficulty_are_skipped(cli):
    write_bank(cli.cards_dir, bank_cards({"hm-1": "hard", "dr-1": "easy"}))
    cli("--dry-run")
    sent = {i for call in cli.calls for i in call["ids"]}
    assert sent == {"hm-2", HM_IN_DRUGS_FILE, "dr-2"}


def test_cli_group_with_nothing_to_tag_is_not_sent(cli):
    write_bank(cli.cards_dir, bank_cards({"dr-1": "easy", "dr-2": "hard"}))
    assert cli("--dry-run") == 0
    assert len(cli.calls) == 1
    assert cli.calls[0]["groups"] == {"hallmarks"}


def test_cli_retag_sends_tagged_cards_too(cli):
    write_bank(cli.cards_dir, bank_cards({"hm-1": "hard", "dr-1": "easy"}))
    cli("--dry-run", "--retag")
    sent = {i for call in cli.calls for i in call["ids"]}
    assert sent == {*HM, HM_IN_DRUGS_FILE, *DR}


def test_cli_retag_overwrites_an_old_difficulty(cli):
    write_bank(cli.cards_dir, bank_cards({"hm-1": "hard"}))
    assert cli("--retag") == 0
    assert by_id(cli.cards_dir)["hm-1"].difficulty == "easy"


def test_cli_nothing_to_tag_makes_no_call_and_exits_0(cli):
    levels = {i: "easy" for i in [*HM, HM_IN_DRUGS_FILE, *DR]}
    write_bank(cli.cards_dir, bank_cards(levels))
    before = {p.name: p.read_bytes() for p in cli.cards_dir.iterdir()}
    assert cli() == 0
    assert cli.calls == []
    assert {p.name: p.read_bytes() for p in cli.cards_dir.iterdir()} == before


def test_cli_prints_a_line_per_card_and_a_summary_per_group(cli, capsys):
    write_bank(cli.cards_dir, bank_cards())
    cli("--dry-run", levels={"hm-2": "hard", "dr-1": "hard"})
    lines = [line.strip() for line in capsys.readouterr().out.splitlines()]
    assert "easy hm-1" in lines
    assert "hard hm-2 (not in the primer)" in lines
    assert f"easy {HM_IN_DRUGS_FILE}" in lines
    assert "hard dr-1 (not in the primer)" in lines
    assert "easy dr-2" in lines
    assert "hallmarks: 2 easy, 1 hard" in lines
    assert "drugs: 1 easy, 1 hard" in lines


def test_cli_prints_the_claude_cost_line(cli, capsys):
    write_bank(cli.cards_dir, bank_cards())
    cli("--dry-run")
    assert "Claude calls" in capsys.readouterr().out


def test_cli_prints_the_model_line_when_something_was_tagged(cli, capsys):
    write_bank(cli.cards_dir, bank_cards())
    cli("--dry-run")
    lines = [line.strip() for line in capsys.readouterr().out.splitlines()]
    assert f"sonnet (prompt v{block.PROMPT_VERSION})" in lines


def test_cli_no_model_line_when_nothing_was_tagged(cli, capsys):
    levels = {i: "easy" for i in [*HM, HM_IN_DRUGS_FILE, *DR]}
    write_bank(cli.cards_dir, bank_cards(levels))
    assert cli() == 0
    assert "(prompt v" not in capsys.readouterr().out


# writing


def test_cli_writes_difficulty_and_files_load_back(cli):
    write_bank(cli.cards_dir, bank_cards())
    assert cli(levels={"hm-2": "hard", "dr-1": "hard"}) == 0
    cards = by_id(cli.cards_dir)
    assert {i: c.difficulty for i, c in cards.items()} == {
        "hm-1": "easy",
        "hm-2": "hard",
        HM_IN_DRUGS_FILE: "easy",
        "dr-1": "hard",
        "dr-2": "easy",
    }


def test_cli_each_line_is_model_dump_json_in_the_same_order(cli):
    files = bank_cards()
    write_bank(cli.cards_dir, files)
    cli(levels={"dr-1": "hard"})
    levels = {"dr-1": "hard"}
    for name, cards in files.items():
        expected = [
            c.model_copy(
                update={"difficulty": levels.get(c.id, "easy")}
            ).model_dump_json()
            for c in cards
        ]
        assert file_lines(cli.cards_dir / name) == expected


def test_cli_other_cards_lines_are_unchanged_in_content_and_order(cli):
    files = bank_cards({"hm-1": "hard", "dr-2": "easy"})
    write_bank(cli.cards_dir, files)
    before = {name: file_lines(cli.cards_dir / name) for name in files}
    assert cli() == 0
    after = {name: file_lines(cli.cards_dir / name) for name in files}
    assert after["hallmarks.jsonl"][0] == before["hallmarks.jsonl"][0]  # hm-1
    assert after["drugs.jsonl"][2] == before["drugs.jsonl"][2]  # dr-2
    for name, cards in files.items():
        assert [json.loads(line)["id"] for line in after[name]] == [c.id for c in cards]


def test_cli_dry_run_writes_nothing(cli):
    write_bank(cli.cards_dir, bank_cards())
    before = {p.name: p.read_bytes() for p in cli.cards_dir.iterdir()}
    assert cli("--dry-run") == 0
    assert len(cli.calls) == 2  # still asks
    assert {p.name: p.read_bytes() for p in cli.cards_dir.iterdir()} == before


def test_cli_leaves_no_tmp_file(cli):
    write_bank(cli.cards_dir, bank_cards())
    assert cli() == 0
    assert sorted(p.name for p in cli.cards_dir.iterdir()) == [
        "drugs.jsonl",
        "hallmarks.jsonl",
    ]


# failures


def one_line_output(capsys) -> str:
    captured = capsys.readouterr()
    return (captured.out + captured.err).strip()


def test_cli_missing_primer_exits_1_without_tag_call(cli, capsys):
    write_bank(cli.cards_dir, bank_cards())
    before = {p.name: p.read_bytes() for p in cli.cards_dir.iterdir()}
    assert cli(primer_error=FileNotFoundError("primer.pdf")) == 1
    assert cli.calls == []
    text = one_line_output(capsys)
    assert text and len(text.splitlines()) == 1
    assert {p.name: p.read_bytes() for p in cli.cards_dir.iterdir()} == before


def test_cli_primer_load_runtime_error_exits_1_without_tag_call(cli, capsys):
    """Any error from reading the PDF (not just OSError) is one line, exit 1."""
    write_bank(cli.cards_dir, bank_cards())
    before = {p.name: p.read_bytes() for p in cli.cards_dir.iterdir()}
    assert cli(primer_error=RuntimeError("broken pdf stream")) == 1
    assert cli.calls == []
    text = one_line_output(capsys)
    assert text and len(text.splitlines()) == 1
    assert {p.name: p.read_bytes() for p in cli.cards_dir.iterdir()} == before


def test_cli_primer_with_only_blank_pages_exits_1_without_tag_call(cli, capsys):
    """A scan: pages but no text on any of them."""
    write_bank(cli.cards_dir, bank_cards())
    before = {p.name: p.read_bytes() for p in cli.cards_dir.iterdir()}
    assert cli(pages=["", "   \n\t", "\n"]) == 1
    assert cli.calls == []
    text = one_line_output(capsys)
    assert text and len(text.splitlines()) == 1
    assert {p.name: p.read_bytes() for p in cli.cards_dir.iterdir()} == before


def test_cli_bad_card_line_exits_1_without_tag_call(cli, capsys):
    write_bank(cli.cards_dir, bank_cards())
    (cli.cards_dir / "zzz.jsonl").write_text("not json\n", encoding="utf-8")
    assert cli() == 1
    assert cli.calls == []
    text = one_line_output(capsys)
    assert len(text.splitlines()) == 1
    assert "zzz.jsonl" in text


def test_cli_repeated_id_exits_1_without_tag_call(cli, capsys):
    write_bank(cli.cards_dir, bank_cards())
    write_bank(cli.cards_dir, {"zzz.jsonl": [make_card("hm-1")]})
    assert cli() == 1
    assert cli.calls == []
    assert len(one_line_output(capsys).splitlines()) == 1


def test_cli_claude_error_for_one_group_others_still_written(cli, capsys):
    files = bank_cards()
    write_bank(cli.cards_dir, files)
    assert cli(raises_for="drugs") == 1
    assert len(cli.calls) == 2  # the other group went on
    cards = by_id(cli.cards_dir)
    assert cards["dr-1"].difficulty is None
    assert cards["dr-2"].difficulty is None
    assert cards["hm-1"].difficulty == "easy"
    assert cards["hm-2"].difficulty == "easy"
    assert cards[HM_IN_DRUGS_FILE].difficulty == "easy"  # in drugs.jsonl, still written
    out = capsys.readouterr()
    error_lines = [
        line
        for line in (out.out + out.err).splitlines()
        if "drugs" in line and "claude broke" in line.lower()
    ]
    assert len(error_lines) == 1


def test_cli_file_changed_during_run_is_not_written(cli, capsys):
    write_bank(cli.cards_dir, bank_cards())
    edited = cli.cards_dir / "hallmarks.jsonl"

    def edit(group):
        if not edit.done:  # the user edits the file while Claude is busy
            edit.done = True
            text = edited.read_text(encoding="utf-8")
            edited.write_text(
                text + make_card("hm-new").model_dump_json() + "\n", encoding="utf-8"
            )

    edit.done = False
    assert cli(during=edit) == 1
    edited_text = edited.read_text(encoding="utf-8")
    assert "hm-new" in edited_text  # the user's edit is kept
    assert all(
        json.loads(line).get("difficulty") is None for line in file_lines(edited)
    )
    assert (
        by_id(cli.cards_dir)["dr-1"].difficulty == "easy"
    )  # the other file is written
    out = capsys.readouterr()
    text = out.out + out.err
    assert "hallmarks.jsonl" in text
    assert "changed during the run" in text
    assert not list(cli.cards_dir.glob("*.tmp"))


def test_cli_exit_0_when_everything_sent_was_tagged(cli):
    write_bank(cli.cards_dir, bank_cards())
    assert cli(levels={"hm-1": "hard"}) == 0


def test_cli_never_prints_or_writes_the_primer_text(cli, capsys):
    secret = "Zebrafish regrow their hearts after the quokka festival of 1987."
    write_bank(cli.cards_dir, bank_cards())
    pages = [PAGE_1, secret, PAGE_3]
    assert cli(pages=pages, levels={"hm-2": "hard"}) == 0
    assert cli.calls and all(call["pages"] == pages for call in cli.calls)
    out = capsys.readouterr()
    texts = [out.out + out.err]
    texts += [p.read_text(encoding="utf-8") for p in cli.cards_dir.iterdir()]
    for text in texts:
        assert secret not in text
        assert "quokka" not in text.lower()


def test_cli_card_id_with_spaces_in_the_file_is_matched_after_stripping(cli):
    write_bank(cli.cards_dir, bank_cards())
    path = cli.cards_dir / "hallmarks.jsonl"
    lines = file_lines(path)
    first = json.loads(lines[0])
    first["id"] = "  hm-1 "
    path.write_text("\n".join([json.dumps(first), *lines[1:]]) + "\n", encoding="utf-8")
    assert cli(levels={"hm-1": "hard"}) == 0
    assert "hm-1" in {i for call in cli.calls for i in call["ids"]}
    cards = by_id(cli.cards_dir)
    assert cards["hm-1"].difficulty == "hard"
    assert cards["hm-2"].difficulty == "easy"
