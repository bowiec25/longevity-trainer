"""Tests for the writer_exam block: contract (ID card + SPEC) and behaviour (from SPEC.md).

The real writer and checker never run: run_writer_exam gets a fake `write` (which
calls the wrapped `check` it receives) and a fake `check`.
"""

import json
from fractions import Fraction
from pathlib import Path

import pytest

import longevity_trainer.blocks.writer_exam as block
from longevity_trainer.blocks.card_bank import ROOT, LongevityCard
from longevity_trainer.blocks.card_checker import (
    PROMPT_VERSION as CHECKER_PROMPT_VERSION,
)
from longevity_trainer.blocks.card_checker import CardVerdict
from longevity_trainer.blocks.card_writer import (
    PROMPT_VERSION as WRITER_PROMPT_VERSION,
)
from longevity_trainer.blocks.card_writer import (
    Drop,
    WriterReport,
    WriterResult,
)
from quizkit.blocks.base import missing_spec_sections, spec_section
from quizkit.claude import ClaudeError
from quizkit.download import DownloadError

SPEC_MD = Path(block.__file__).parent / "SPEC.md"
GATES = {"shape", "ask", "link", "quote", "repeat", "checker"}


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "writer_exam"
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


# ---- Behaviour (from SPEC.md) ----------------------------------------------------
# Called as block.load_jobs / block.run_writer_exam / ... (not imported at the top),
# so the contract tests above still run before the block is built.


@pytest.fixture(autouse=True)
def no_real_primer(monkeypatch):
    """Safety net: the CLI never reads the real primer PDF."""
    from longevity_trainer import cli as cli_module

    def no_primer(*_a, **_k):
        raise FileNotFoundError("no primer in tests")

    monkeypatch.setattr(cli_module, "load_primer", no_primer, raising=False)


def job_line(job_id: str = "taurine", **changes) -> dict:
    data = {
        "id": job_id,
        "topic": job_id,
        "source": "pearl-2025",
        "primer_pages": None,
        "pages": None,
        "asks": None,
        "n": 4,
        "holdout": False,
        "why": "a test job",
    }
    return {**data, **changes}


def make_job(job_id: str = "taurine", **changes):
    return block.ExamJob.model_validate(job_line(job_id, **changes))


def make_card(card_id: str, question: str) -> LongevityCard:
    return LongevityCard.model_validate(
        {
            "id": card_id,
            "kind": "fact",
            "topic": "test",
            "question": question,
            "answers": ["An answer"],
            "receipt": {
                "source": "pearl-2025",
                "quote": "a quote that is long enough to be a key",
                "page": 1,
            },
        }
    )


class Fake:
    """A fake writer and checker.

    plans[topic] is a list of outcomes per draft, or an exception to raise:
    "kept" (checked, the checker says ok), a gate name (dropped there, no check),
    or a list of rule numbers (checked, the checker fails it naming them).
    """

    def __init__(self, plans: dict, checker_errors: dict | None = None):
        self.plans = plans
        self.checker_errors = checker_errors or {}  # topic -> the report's count
        self.calls: list[dict] = []
        self.checked: list[str] = []  # card ids the inner check saw
        self._rules: dict[str, list[int]] = {}

    def check(self, card, **kwargs):
        self.checked.append(card.id)
        rules = self._rules.get(card.id, [])
        if not rules:
            return CardVerdict(ok=True, rules=[], reason="fine")
        return CardVerdict(ok=False, rules=rules, reason=f"breaks {rules}")

    def write(self, topic, source, **kwargs):
        self.calls.append({"topic": topic, "source": source, **kwargs})
        plan = self.plans.get(topic, [])
        if isinstance(plan, BaseException):
            raise plan
        check = kwargs["check"]
        kept, drops = [], []
        for i, outcome in enumerate(plan):
            card = make_card(
                f"{topic}-what-{i + 1}", f"Question number {i} on {topic}?"
            )
            if outcome == "kept" or isinstance(outcome, list):
                self._rules[card.id] = [] if outcome == "kept" else outcome
                verdict = check(card)
                if verdict.ok:
                    kept.append(card)
                else:
                    drops.append(
                        Drop(question=card.question, gate="checker", reason="x")
                    )
            else:
                drops.append(Drop(question=card.question, gate=outcome, reason="x"))
        count = {g: sum(d.gate == g for d in drops) for g in GATES}
        report = WriterReport(
            drafted=len(plan),
            kept=len(kept),
            dropped_shape=count["shape"],
            dropped_link=count["link"],
            dropped_quote=count["quote"],
            dropped_repeat=count["repeat"],
            dropped_checker=count["checker"],
            dropped_ask=count["ask"],
            checker_errors=self.checker_errors.get(topic, 0),
            asks_kept=["what"] if kept else [],
            model=kwargs.get("model", "sonnet"),
        )
        return WriterResult(kept=kept, drops=drops, report=report)


def run(plans: dict, jobs=None, primer=None, model="sonnet", checker_errors=None):
    """(report, printed lines, fake) for one job per topic in plans."""
    fake = Fake(plans, checker_errors)
    if jobs is None:
        jobs = [make_job(topic) for topic in plans]
    lines: list[str] = []
    report = block.run_writer_exam(
        jobs,
        write=fake.write,
        check=fake.check,
        primer=primer,
        show=lines.append,
        model=model,
    )
    return report, lines, fake


# -- Constants ---------------------------------------------------------------------


def test_constants():
    assert block.MIN_KEPT_SHARE == Fraction(2, 5)
    assert isinstance(block.MIN_KEPT_SHARE, Fraction)
    assert block.MAX_EMPTY_JOBS == 1
    assert block.JOBS_FILE == ROOT / "tests" / "data" / "writer_exam.jsonl"


# -- load_jobs ---------------------------------------------------------------------


def write_lines(tmp_path, lines: list[str]) -> Path:
    path = tmp_path / "jobs.jsonl"
    path.write_text("\n".join(lines) + "\n", "utf-8")
    return path


def test_load_jobs_reads_a_good_file_skipping_blank_lines(tmp_path):
    path = write_lines(
        tmp_path,
        [
            json.dumps(job_line("a")),
            "",
            "   ",
            json.dumps(
                job_line(
                    "b-2",
                    primer_pages=[3, 4],
                    pages=[1, 2],
                    asks=["how"],
                    n=20,
                    holdout=True,
                )
            ),
        ],
    )
    jobs = block.load_jobs(path)
    assert [j.id for j in jobs] == ["a", "b-2"]
    assert all(isinstance(j, block.ExamJob) for j in jobs)
    b = jobs[1]
    assert list(b.primer_pages) == [3, 4]
    assert list(b.pages) == [1, 2]
    assert list(b.asks) == ["how"]
    assert (b.n, b.holdout) == (20, True)
    assert jobs[0].primer_pages is None and jobs[0].asks is None


def test_load_jobs_reads_json_arrays_for_page_ranges(tmp_path):
    path = write_lines(
        tmp_path, [json.dumps(job_line("a", primer_pages=[34, 35], pages=[1, 9]))]
    )
    (job,) = block.load_jobs(path)
    assert list(job.primer_pages) == [34, 35]
    assert list(job.pages) == [1, 9]


def test_exam_job_built_in_python_accepts_lists():
    """Strictness is about reading the file; Python lists still build a job."""
    job = block.ExamJob(
        id="py", topic="py", source="pearl-2025", why="w", primer_pages=[2, 3]
    )
    assert list(job.primer_pages) == [2, 3]


def test_exam_job_is_frozen():
    job = make_job()
    with pytest.raises(Exception):  # noqa: B017 - pydantic's frozen error
        job.n = 5


def _without(key: str) -> dict:
    data = job_line("x2")
    del data[key]
    return data


BAD_JOB_LINES = {
    "not json": "{not json",
    "missing topic": json.dumps(_without("topic")),
    "missing why": json.dumps(_without("why")),
    "extra field": json.dumps(job_line("x2", colour="red")),
    "n 0": json.dumps(job_line("x2", n=0)),
    "n 21": json.dumps(job_line("x2", n=21)),
    "bad asks value": json.dumps(job_line("x2", asks=["why"])),
    "primer_pages backwards": json.dumps(job_line("x2", primer_pages=[5, 3])),
    "pages backwards": json.dumps(job_line("x2", pages=[5, 3])),
    "pages from 0": json.dumps(job_line("x2", pages=[0, 3])),
    "repeated id": json.dumps(job_line("x1")),
    "empty why": json.dumps(job_line("x2", why="")),
    "id with a space": json.dumps(job_line("x 2")),
    "n as a string": json.dumps(job_line("x2", n="4")),
    "holdout as a string": json.dumps(job_line("x2", holdout="yes")),
    "primer_pages with a string": json.dumps(job_line("x2", primer_pages=["34", 35])),
    "pages with a string": json.dumps(job_line("x2", pages=[1, "2"])),
}


@pytest.mark.parametrize("bad", BAD_JOB_LINES.values(), ids=BAD_JOB_LINES.keys())
def test_bad_job_line_names_the_file_and_line(tmp_path, bad):
    path = write_lines(tmp_path, [json.dumps(job_line("x1")), bad])
    with pytest.raises(ValueError, match=r"line 2\b") as exc:
        block.load_jobs(path)
    assert path.name in str(exc.value)


def test_empty_jobs_file_raises(tmp_path):
    path = tmp_path / "jobs.jsonl"
    path.write_text("", "utf-8")
    with pytest.raises(ValueError):
        block.load_jobs(path)


def test_jobs_file_of_blank_lines_raises(tmp_path):
    path = write_lines(tmp_path, ["", "  "])
    with pytest.raises(ValueError):
        block.load_jobs(path)


def test_real_jobs_file_loads_with_enough_jobs():
    jobs = block.load_jobs()
    assert len([j for j in jobs if not j.holdout]) >= 6
    assert len([j for j in jobs if j.holdout]) >= 2
    assert len({j.id for j in jobs}) == len(jobs)
    for job in jobs:
        assert (ROOT / "data" / "sources" / f"{job.source}.json").is_file(), job.id
        assert job.why.strip()


def test_only_id_topic_source_why_are_required(tmp_path):
    line = {"id": "short", "topic": "short", "source": "pearl-2025", "why": "w"}
    path = write_lines(tmp_path, [json.dumps(line)])
    (job,) = block.load_jobs(path)
    assert (job.n, job.holdout) == (4, False)
    assert job.pages is None and job.primer_pages is None and job.asks is None


def test_load_jobs_does_not_check_sources(tmp_path):
    path = write_lines(tmp_path, [json.dumps(job_line("a", source="no-such-source"))])
    (job,) = block.load_jobs(path)
    assert job.source == "no-such-source"


def test_load_jobs_defaults_to_jobs_file():
    assert block.load_jobs() == block.load_jobs(block.JOBS_FILE)


# -- Calling the writer ------------------------------------------------------------


def test_write_gets_the_jobs_settings():
    job = make_job(
        "cgm", source="cgm-healthy-2022", pages=[2, 5], asks=["how", "catch"], n=7
    )
    _, _, fake = run({"cgm": ["kept"]}, jobs=[job], model="haiku")
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert (call["topic"], call["source"]) == ("cgm", "cgm-healthy-2022")
    assert call["n"] == 7
    assert call["model"] == "haiku"
    assert tuple(call["pages"]) == (2, 5)
    assert list(call["only_asks"]) == ["how", "catch"]
    assert call["taken_ids"] == set()
    assert call["taken_questions"] == set()
    assert callable(call["check"])
    assert "bank" not in call and "cards" not in call


def test_write_gets_none_for_pages_and_asks_when_null():
    _, _, fake = run({"taurine": ["kept"]})
    call = fake.calls[0]
    assert call["pages"] is None
    assert call["only_asks"] is None


def test_primer_text_is_built_from_the_chosen_pages():
    primer = ["page one text", "page two text", "page three text", "page four"]
    job = make_job("taurine", primer_pages=[2, 3])
    _, _, fake = run({"taurine": ["kept"]}, jobs=[job], primer=primer)
    assert fake.calls[0]["primer_text"] == (
        "[primer page 2]\npage two text\n\n[primer page 3]\npage three text"
    )


def test_job_without_primer_pages_gets_empty_primer_text():
    _, _, fake = run({"taurine": ["kept"]}, primer=["page one"])
    assert fake.calls[0]["primer_text"] == ""


def test_each_job_gets_fresh_taken_sets():
    _, _, fake = run({"a": ["kept"], "b": ["kept"]})
    assert [c["taken_ids"] for c in fake.calls] == [set(), set()]
    assert [c["taken_questions"] for c in fake.calls] == [set(), set()]


# -- Counting ----------------------------------------------------------------------


def test_job_scores_and_totals_add_up():
    plans = {
        "a": ["kept", "kept", "quote", "repeat", [3]],
        "b": ["kept", "shape", "ask", "link", [4], [3, 4]],
    }
    report, _, _ = run(plans)
    assert isinstance(report, block.WriterExamReport)
    a, b = report.jobs
    assert isinstance(a, block.JobScore)
    assert (a.id, a.drafted, a.kept, a.niche, a.error) == ("a", 5, 2, 0, "")
    assert a.dropped == {
        "shape": 0,
        "ask": 0,
        "link": 0,
        "quote": 1,
        "repeat": 1,
        "checker": 1,
    }
    assert (b.drafted, b.kept, b.niche) == (6, 1, 2)
    assert b.dropped == {
        "shape": 1,
        "ask": 1,
        "link": 1,
        "quote": 0,
        "repeat": 0,
        "checker": 2,
    }
    assert (report.drafted, report.kept, report.niche) == (11, 3, 2)
    assert report.dropped == {g: a.dropped[g] + b.dropped[g] for g in GATES}


def test_every_gate_is_a_key_even_when_zero():
    report, _, _ = run({"a": ["kept"]})
    assert set(report.jobs[0].dropped) == GATES
    assert set(report.dropped) == GATES


@pytest.mark.parametrize(
    ("rules", "niche"), [([3], 0), ([4], 1), ([3, 4], 1), ([2, 5, 6], 0)]
)
def test_niche_counts_checker_fails_naming_rule_4(rules, niche):
    report, _, _ = run({"a": ["kept", rules]})
    assert report.jobs[0].niche == niche
    assert report.niche == niche


def test_niche_is_counted_through_the_wrapped_check():
    """The writer gets a wrapper: calling it reaches the inner check."""
    report, _, fake = run({"a": [[4], "kept"]})
    assert fake.calls[0]["check"] is not fake.check
    assert fake.checked == ["a-what-1", "a-what-2"]
    assert report.jobs[0].niche == 1


def test_niche_is_counted_per_job():
    report, _, _ = run({"a": [[4], [4]], "b": ["kept", [3]]})
    assert [j.niche for j in report.jobs] == [2, 0]
    assert report.niche == 2


def test_holdout_flag_is_carried_into_the_score():
    jobs = [make_job("a"), make_job("b", holdout=True)]
    report, _, _ = run({"a": ["kept"], "b": ["kept"]}, jobs=jobs)
    assert [j.holdout for j in report.jobs] == [False, True]


def test_report_records_model_and_writer_prompt_version():
    report, _, _ = run({"a": ["kept"]}, model="haiku")
    assert report.model == "haiku"
    assert report.prompt_version == WRITER_PROMPT_VERSION
    assert report.checker_prompt_version == CHECKER_PROMPT_VERSION


def test_checker_errors_come_from_the_writer_report_and_are_totalled():
    report, _, _ = run(
        {"a": ["kept"] * 4, "b": ["kept"] * 4, "c": ["kept"] * 4},
        checker_errors={"a": 2, "c": 1},
    )
    assert [j.checker_errors for j in report.jobs] == [2, 0, 1]
    assert report.checker_errors == 3


def test_scores_and_report_are_frozen():
    report, _, _ = run({"a": ["kept"]})
    with pytest.raises(Exception):  # noqa: B017 - pydantic's frozen error
        report.kept = 99
    with pytest.raises(Exception):  # noqa: B017
        report.jobs[0].kept = 99


# -- The bar -----------------------------------------------------------------------


@pytest.mark.parametrize(("kept", "passed"), [(4, True), (3, False)])
def test_bar_kept_share(kept, passed):
    report, _, _ = run({"a": ["kept"] * kept + ["repeat"] * (10 - kept)})
    assert (report.kept, report.drafted) == (kept, 10)
    assert report.passed is passed


@pytest.mark.parametrize(
    ("kept", "drafted", "passed"), [(2, 5, True), (39, 100, False), (40, 100, True)]
)
def test_bar_is_an_exact_two_fifths(kept, drafted, passed):
    report, _, _ = run({"a": ["kept"] * kept + ["repeat"] * (drafted - kept)})
    assert (report.kept, report.drafted) == (kept, drafted)
    assert report.passed is passed


def test_one_checker_error_fails():
    report, _, _ = run({"a": ["kept"] * 9 + ["repeat"]}, checker_errors={"a": 1})
    assert (report.errors, report.empty_jobs, report.dropped["quote"]) == (0, 0, 0)
    assert report.checker_errors == 1
    assert report.passed is False


def test_one_empty_job_passes():
    report, _, _ = run({"a": ["kept"] * 8, "b": ["repeat", "repeat"]})
    assert report.empty_jobs == 1
    assert report.passed is True


def test_two_empty_jobs_fail():
    report, _, _ = run({"a": ["kept"] * 8, "b": ["repeat"], "c": ["shape"]})
    assert (report.kept, report.drafted) == (8, 10)
    assert report.empty_jobs == 2
    assert report.passed is False


def test_one_quote_not_found_fails():
    report, _, _ = run({"a": ["kept"] * 9 + ["quote"]})
    assert report.dropped["quote"] == 1
    assert report.passed is False


def test_one_error_fails():
    report, _, _ = run({"a": ["kept"] * 8, "b": ClaudeError("timed out")})
    assert report.errors == 1
    assert report.passed is False


def test_no_jobs_fails():
    report, lines, fake = run({})
    assert report.jobs == []
    assert report.passed is False
    assert fake.calls == [] and lines == []


def test_nothing_drafted_fails():
    report, _, _ = run({"a": []})
    assert report.drafted == 0
    assert report.passed is False


def test_all_good_passes():
    report, _, _ = run({"a": ["kept"] * 4, "b": ["kept"] * 3 + [[3]]})
    assert (report.errors, report.empty_jobs) == (0, 0)
    assert report.passed is True


def test_model_dump_includes_passed():
    report, _, _ = run({"a": ["kept"] * 4})
    assert report.model_dump()["passed"] is True


# -- Errors ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "err",
    [
        ClaudeError("claude broke\nmore detail"),
        OSError("disk gone\nmore detail"),
        ValueError("bad pages\nmore detail"),
        DownloadError("no download\nmore detail"),
        RuntimeError("something odd\nmore detail"),
    ],
    ids=["claude", "os", "value", "download", "other"],
)
def test_write_raising_scores_an_error_and_later_jobs_run(err):
    report, _, fake = run({"a": err, "b": ["kept"] * 4})
    a, b = report.jobs
    assert a.error == str(err).splitlines()[0]
    assert "\n" not in a.error
    assert (a.drafted, a.kept) == (0, 0)
    assert (report.errors, report.empty_jobs) == (1, 1)
    assert [c["topic"] for c in fake.calls] == ["a", "b"]
    assert (b.kept, b.error) == (4, "")
    assert report.passed is False


def test_error_skips_a_leading_newline():
    report, _, _ = run({"a": ValueError("\nsource missing"), "b": ["kept"]})
    assert report.jobs[0].error == "source missing"


def test_error_with_an_empty_message_is_the_type_name():
    report, _, _ = run({"a": ValueError(""), "b": ["kept"]})
    assert report.jobs[0].error == "ValueError"
    assert report.errors == 1


class NoReport:
    """Something write might return that has no usable report."""


class BadReport:
    report = "not a report"


@pytest.mark.parametrize(
    "returned",
    [None, NoReport(), BadReport()],
    ids=["none", "no-report-attr", "report-not-a-report"],
)
def test_write_returning_no_usable_report_is_an_error(returned):
    fake = Fake({"b": ["kept"] * 4})
    topics: list[str] = []

    def write(topic, source, **kwargs):
        topics.append(topic)
        if topic == "a":
            return returned
        return fake.write(topic, source, **kwargs)

    report = block.run_writer_exam(
        [make_job("a"), make_job("b")],
        write=write,
        check=fake.check,
        show=lambda _line: None,
    )
    a, b = report.jobs
    assert a.error and "\n" not in a.error
    assert (a.drafted, a.kept) == (0, 0)
    assert (report.errors, report.empty_jobs) == (1, 1)
    assert topics == ["a", "b"]
    assert (b.kept, b.error) == (4, "")


def test_primer_job_whose_pages_are_all_blank_is_an_error():
    jobs = [make_job("a", primer_pages=[2, 3]), make_job("b")]
    primer = ["one", "", "  \n ", "four"]
    report, _, fake = run({"a": ["kept"], "b": ["kept"] * 4}, jobs=jobs, primer=primer)
    assert report.jobs[0].error
    assert [c["topic"] for c in fake.calls] == ["b"]
    assert (report.errors, report.empty_jobs) == (1, 1)


def test_primer_job_without_a_primer_is_an_error_without_calling_write():
    jobs = [make_job("a", primer_pages=[1, 2]), make_job("b")]
    report, _, fake = run({"a": ["kept"], "b": ["kept"] * 4}, jobs=jobs)
    assert report.jobs[0].error
    assert "\n" not in report.jobs[0].error
    assert [c["topic"] for c in fake.calls] == ["b"]
    assert (report.errors, report.empty_jobs) == (1, 1)
    assert report.passed is False


def test_primer_pages_past_the_end_is_an_error_without_calling_write():
    jobs = [make_job("a", primer_pages=[3, 4]), make_job("b")]
    primer = ["one", "two", "three"]
    report, _, fake = run({"a": ["kept"], "b": ["kept"] * 4}, jobs=jobs, primer=primer)
    assert report.jobs[0].error
    assert [c["topic"] for c in fake.calls] == ["b"]
    assert report.errors == 1


# -- Output ------------------------------------------------------------------------


def test_one_line_per_job_in_the_spec_format():
    plans = {
        "a": ["kept", "kept", "quote", "repeat", "shape", "ask", "link", [4], [3]],
        "b": ValueError("boom\nsecond line"),
    }
    _, lines, _ = run(plans)
    assert lines == [
        (
            "a: kept 2/9; dropped quote 1, checker 2 (niche 1), repeat 1, shape 1, "
            "ask 1, link 1"
        ),
        "b: error: boom",
    ]


def test_job_line_ends_with_checker_errors_only_when_some():
    _, lines, _ = run({"a": ["kept"], "b": ["kept"]}, checker_errors={"b": 2})
    assert "checker errors" not in lines[0]
    assert lines[1] == (
        "b: kept 1/1; dropped quote 0, checker 0 (niche 0), repeat 0, shape 0, "
        "ask 0, link 0; checker errors 2"
    )


def test_zero_counts_are_still_printed():
    _, lines, _ = run({"a": ["kept"]})
    assert lines == [
        (
            "a: kept 1/1; dropped quote 0, checker 0 (niche 0), repeat 0, shape 0, "
            "ask 0, link 0"
        )
    ]


# -- CLI ---------------------------------------------------------------------------


def cli_jobs():
    return [
        make_job("m1"),
        make_job("m2"),
        make_job("h1", holdout=True),
        make_job("m3"),
        make_job("h2", holdout=True),
    ]


def real_report(passing: bool):
    plan = ["kept"] * 4 + ["repeat"] * 6 if passing else ["kept"] * 3 + ["repeat"] * 7
    report, _, _ = run({"a": plan})
    assert report.passed is passing
    return report


@pytest.fixture
def cli_env(monkeypatch):
    """Replace load_jobs and run_writer_exam on the cli module; record the calls."""
    from longevity_trainer import cli

    seen: list[dict] = []
    state = {"report": real_report(True), "jobs": cli_jobs()}

    def fake_load_jobs(*_a, **_k):
        return state["jobs"]

    def fake_run(jobs, **kwargs):
        seen.append({"jobs": list(jobs), **kwargs})
        return state["report"]

    monkeypatch.setattr(cli, "load_jobs", fake_load_jobs, raising=False)
    monkeypatch.setattr(cli, "run_writer_exam", fake_run, raising=False)
    return cli.main, seen, state


def test_cli_runs_only_main_jobs_by_default(cli_env):
    main, seen, _ = cli_env
    assert main(["writer-exam"]) == 0
    assert len(seen) == 1
    assert [j.id for j in seen[0]["jobs"]] == ["m1", "m2", "m3"]


def test_cli_holdout_runs_only_holdout_jobs(cli_env):
    main, seen, _ = cli_env
    main(["writer-exam", "--holdout"])
    assert [j.id for j in seen[0]["jobs"]] == ["h1", "h2"]


def test_cli_limit_1_passes_one_job(cli_env):
    main, seen, _ = cli_env
    main(["writer-exam", "--limit", "1"])
    assert [j.id for j in seen[0]["jobs"]] == ["m1"]


def test_cli_holdout_with_limit(cli_env):
    main, seen, _ = cli_env
    main(["writer-exam", "--holdout", "--limit", "1"])
    assert [j.id for j in seen[0]["jobs"]] == ["h1"]


def test_cli_passes_the_model(cli_env):
    main, seen, _ = cli_env
    main(["writer-exam", "--model", "haiku"])
    assert seen[0]["model"] == "haiku"


def test_cli_dry_run_lists_jobs_and_calls_nothing(cli_env, monkeypatch, capsys):
    from longevity_trainer import cli

    main, seen, _ = cli_env

    def no_claude(*a, **k):
        raise AssertionError("dry run called Claude")

    monkeypatch.setattr(cli, "ask_claude", no_claude)
    assert main(["writer-exam", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert seen == []
    for job_id in ["m1", "m2", "m3"]:
        assert job_id in out
    assert "h1" not in out and "h2" not in out


@pytest.mark.parametrize(("passing", "code"), [(True, 0), (False, 1)])
def test_cli_exit_code_follows_passed(cli_env, passing, code):
    main, _, state = cli_env
    state["report"] = real_report(passing)
    assert main(["writer-exam"]) == code


def test_cli_prints_the_totals_and_cost_lines(cli_env, capsys):
    main, _, _ = cli_env
    main(["writer-exam"])
    out = capsys.readouterr().out
    totals = (
        f"sonnet (writer prompt v{WRITER_PROMPT_VERSION}, "
        f"checker prompt v{CHECKER_PROMPT_VERSION}): kept 4/10 (40%); niche 0; "
        "empty jobs 0; quotes not found 0; checker errors 0; errors 0 -> PASSED"
    )
    assert totals in out
    lines = out.strip().splitlines()
    assert lines.index(next(ln for ln in lines if totals in ln)) < len(lines) - 1
    assert "Claude calls" in lines[-1]


def test_cli_not_passed_says_not_passed(cli_env, capsys):
    main, _, state = cli_env
    state["report"] = real_report(False)
    main(["writer-exam"])
    assert "-> NOT PASSED" in capsys.readouterr().out


@pytest.mark.parametrize("limit", ["0", "-1", "x"])
def test_cli_bad_limit_exits_2(cli_env, limit):
    main, seen, _ = cli_env
    with pytest.raises(SystemExit) as exc:
        main(["writer-exam", "--limit", limit])
    assert exc.value.code == 2
    assert seen == []


def test_cli_does_not_read_the_primer_when_no_job_needs_it(cli_env, monkeypatch):
    """Assumes the CLI reads the primer through `cli.load_primer`, as write-cards."""
    from longevity_trainer import cli

    main, seen, _ = cli_env

    def refuse(*_a, **_k):
        pytest.fail("read the primer though no chosen job needs it")

    monkeypatch.setattr(cli, "load_primer", refuse)
    main(["writer-exam"])
    assert len(seen) == 1


def test_cli_never_writes_cards(cli_env, monkeypatch, tmp_path):
    from longevity_trainer import cli

    main, _, _ = cli_env
    cards = tmp_path / "cards"
    monkeypatch.setattr(cli, "CARDS_DIR", cards, raising=False)
    main(["writer-exam"])
    assert not cards.exists() or not any(cards.iterdir())


def test_cli_bad_jobs_file_runs_nothing(cli_env, monkeypatch):
    from longevity_trainer import cli

    main, seen, _ = cli_env

    def bad(*_a, **_k):
        raise ValueError("writer_exam.jsonl line 3: bad")

    monkeypatch.setattr(cli, "load_jobs", bad)
    try:
        code = main(["writer-exam"])
    except ValueError:
        code = None
    assert seen == []
    assert code != 0


def test_cli_totals_percent_is_a_whole_number(cli_env, capsys):
    main, _, state = cli_env
    report, _, _ = run({"a": ["kept"] + ["repeat"] * 2})
    state["report"] = report
    main(["writer-exam"])
    out = capsys.readouterr().out
    assert "kept 1/3 (33%)" in out
    assert "33." not in out


def test_cli_totals_percent_is_rounded_down(cli_env, capsys):
    """21 of 53 is 39.6%: prints 39%, never 40% (which would look like the bar)."""
    main, _, state = cli_env
    report, _, _ = run({"a": ["kept"] * 21 + ["repeat"] * 32})
    state["report"] = report
    main(["writer-exam"])
    out = capsys.readouterr().out
    assert "kept 21/53 (39%)" in out
    assert "(40%)" not in out


def test_cli_totals_show_checker_errors(cli_env, capsys):
    main, _, state = cli_env
    report, _, _ = run({"a": ["kept"] * 4 + ["repeat"] * 6}, checker_errors={"a": 3})
    state["report"] = report
    assert main(["writer-exam"]) == 1
    out = capsys.readouterr().out
    assert "; checker errors 3; errors 0 -> NOT PASSED" in out


def test_cli_bad_jobs_file_prints_one_line_and_exits_1(cli_env, monkeypatch, capsys):
    from longevity_trainer import cli

    main, seen, _ = cli_env

    def bad(*_a, **_k):
        raise ValueError("writer_exam.jsonl line 3: bad")

    monkeypatch.setattr(cli, "load_jobs", bad)
    assert main(["writer-exam"]) == 1
    assert seen == []
    captured = capsys.readouterr()
    printed = [ln for ln in (captured.out + captured.err).splitlines() if ln.strip()]
    assert len(printed) == 1
