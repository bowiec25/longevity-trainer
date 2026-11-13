"""Contract test for the web_launch block: its ID card and SPEC.md are complete.

Plus behaviour tests from SPEC.md: a fake Streamlit process, a fake address check,
a no-op sleep and a list as the browser. The real Streamlit is never started; the
only network use is `port_answers` against a socket this test binds on 127.0.0.1.
"""

import re
import socket
import subprocess
import sys
from pathlib import Path

import pytest

import quizkit.blocks.web_launch as block
from quizkit.blocks.base import missing_spec_sections, spec_section

SPEC_MD = Path(block.__file__).parent / "SPEC.md"


def test_block_spec_matches():
    assert block.BLOCK_SPEC.name == "web_launch"
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


# --- constants, command, url ----------------------------------------------------

URL = "http://127.0.0.1:8501"
PAGE = Path("some") / "web_app.py"


def test_constants():
    assert block.HOST == "127.0.0.1"
    assert block.PORT == 8501
    assert block.WAIT == 30.0


def test_url_default():
    assert block.url() == URL


def test_url_given_host_and_port():
    assert block.url("127.0.0.1", 9000) == "http://127.0.0.1:9000"


def test_command_runs_the_page_with_streamlit():
    cmd = block.command(PAGE)
    assert cmd[:5] == [sys.executable, "-m", "streamlit", "run", str(PAGE)]
    assert all(isinstance(part, str) for part in cmd)


def test_command_has_every_local_only_flag():
    cmd = block.command(PAGE)
    assert "--server.address=127.0.0.1" in cmd  # this computer only
    assert "--server.port=8501" in cmd
    assert "--server.headless=true" in cmd  # no first-run email question
    assert "--browser.gatherUsageStats=false" in cmd  # no usage data
    assert "--client.toolbarMode=minimal" in cmd  # no Deploy button


def test_command_uses_the_port_and_host_given():
    cmd = block.command(PAGE, host="127.0.0.1", port=9123)
    assert "--server.port=9123" in cmd
    assert "--server.port=8501" not in cmd
    assert "--server.address=127.0.0.1" in cmd


# --- serve: fakes -----------------------------------------------------------------


class FakeProcess:
    """Stands in for Streamlit: `poll`, `wait`, `kill`, no real process."""

    def __init__(
        self, command, cwd, code=0, stops_early=False, ctrl_c=0, hangs=False, slow=0
    ):
        self.command, self.cwd, self.code = command, cwd, code
        self.slow = slow  # this many short waits time out before it exits
        self.timeouts = []  # the timeout passed to each `wait` call
        self.stops_early, self.ctrl_c, self.hangs = stops_early, ctrl_c, hangs
        self.killed = False
        self.waits_after_kill = 0

    def poll(self):
        return self.code if self.stops_early else None

    def wait(self, timeout=None):
        self.timeouts.append(timeout)
        if self.slow:
            self.slow -= 1
            raise subprocess.TimeoutExpired(self.command, timeout)
        if self.killed:
            self.waits_after_kill += 1
            return self.code
        if self.ctrl_c:  # the user presses Ctrl-C while we wait
            self.ctrl_c -= 1
            raise KeyboardInterrupt
        if self.hangs:
            raise subprocess.TimeoutExpired(self.command, timeout)
        return self.code

    def kill(self):
        self.killed = True


class Harness:
    """Runs `serve` with every outside effect faked and recorded."""

    def __init__(self, answers, otherwise=False, **process):
        self.answers = list(answers)  # what `is_up` says, in order
        self.otherwise = otherwise  # what it says once the list runs out
        self.process_kw = process
        self.started, self.opened, self.lines = [], [], []
        self.checks, self.sleeps = [], []

    def popen(self, command, cwd):
        p = FakeProcess(command, cwd, **self.process_kw)
        self.started.append(p)
        return p

    def is_up(self, host, port):
        self.checks.append((host, port))
        answer = self.answers.pop(0) if self.answers else self.otherwise
        if answer is KeyboardInterrupt:  # the user presses Ctrl-C mid-check
            raise KeyboardInterrupt
        return answer

    def sleep(self, seconds):
        self.sleeps.append(seconds)

    def serve(self, page=PAGE, cwd=Path("project"), **kw):
        return block.serve(
            page,
            cwd,
            write=self.lines.append,
            open_url=self.opened.append,
            popen=self.popen,
            is_up=self.is_up,
            sleep=self.sleep,
            **kw,
        )

    @property
    def output(self):
        return "\n".join(self.lines)


# --- serve: outputs ---------------------------------------------------------------


def test_serve_starts_the_command_in_cwd_opens_once_and_returns_0():
    h = Harness([False, False, True])  # free, still starting, up
    code = h.serve(cwd=Path("project"))
    assert code == 0
    [p] = h.started
    assert p.command == block.command(PAGE)
    assert p.cwd == Path("project")
    assert h.opened == [URL]
    assert f"The quiz is open at {URL} (Ctrl-C here stops it)." in h.lines
    assert not p.killed


def test_serve_checks_the_address_given_every_0_2_s():
    h = Harness([False, False, False, True])
    h.serve(host="127.0.0.1", port=9000)
    assert set(h.checks) == {("127.0.0.1", 9000)}
    assert h.sleeps and all(s == pytest.approx(0.2) for s in h.sleeps)
    assert h.opened == ["http://127.0.0.1:9000"]
    assert h.started[0].command == block.command(PAGE, "127.0.0.1", 9000)


def test_serve_returns_the_process_exit_code():
    h = Harness([False, True], code=3)
    assert h.serve() == 3
    assert h.opened == [URL]


def test_serve_waits_in_short_waits_retried_on_timeout():
    h = Harness([False, True], code=3, slow=2)
    assert h.serve() == 3
    p = h.started[0]
    assert len(p.timeouts) == 3  # two timed out, the third returned 3
    assert all(t == 0.5 for t in p.timeouts)
    assert not p.killed


# --- serve: failure modes ---------------------------------------------------------


def test_port_already_taken_starts_nothing_and_returns_1():
    h = Harness([True])
    assert h.serve() == 1
    assert h.started == []
    assert h.opened == []
    assert f"Something is already running at {URL}." in h.lines
    assert "If it's the quiz, just open that page; otherwise stop it first." in h.lines


def test_streamlit_stopping_before_the_page_answers_opens_nothing():
    h = Harness([False], otherwise=False, code=2, stops_early=True)
    assert h.serve() == 2
    assert h.opened == []
    assert "The quiz is open at" not in h.output


def test_streamlit_not_installed_returns_its_own_exit_code():
    """A broken install looks like a process that exits at once with an error code."""
    h = Harness([False], otherwise=False, code=1, stops_early=True)
    assert h.serve() == 1
    assert h.opened == []


def test_slow_start_says_where_and_opens_nothing():
    h = Harness([False], otherwise=False, code=0)
    code = h.serve(wait=0)
    assert code == 0  # it kept waiting for the process, then returned its code
    assert h.opened == []
    assert f"Streamlit is slow to start: open {URL} once it's ready." in h.lines


def test_ctrl_c_once_lets_streamlit_finish_and_returns_0():
    h = Harness([False, True], code=0, ctrl_c=1)
    assert h.serve() == 0
    assert not h.started[0].killed  # it finished by itself


def test_ctrl_c_once_returns_0_even_if_streamlit_exits_nonzero():
    h = Harness([False, True], code=130, ctrl_c=1)
    assert h.serve() == 0


def test_ctrl_c_in_sleep_during_start_up_returns_0_unopened_not_killed():
    h = Harness([False], otherwise=False, code=130)

    def sleep(seconds):
        raise KeyboardInterrupt

    h.sleep = sleep
    assert h.serve() == 0
    assert h.opened == []
    assert not h.started[0].killed  # it finishes by itself


def test_ctrl_c_in_is_up_during_start_up_returns_0_unopened_not_killed():
    h = Harness([False, False, KeyboardInterrupt], code=130)
    assert h.serve() == 0
    assert h.opened == []
    assert not h.started[0].killed


def test_stopped_process_wins_over_an_answering_address_in_the_same_round():
    """Each round checks the process first: stopped means nothing is opened."""
    h = Harness([False], otherwise=True, code=2, stops_early=True)
    assert h.serve() == 2
    assert h.opened == []
    assert "The quiz is open at" not in h.output


def test_ctrl_c_twice_kills_and_waits_then_returns_0():
    h = Harness([False, True], code=0, ctrl_c=2)
    assert h.serve() == 0
    p = h.started[0]
    assert p.killed
    assert p.waits_after_kill >= 1  # nothing left holding the port


def test_hanging_after_ctrl_c_is_killed_and_waited_for():
    h = Harness([False, True], code=0, ctrl_c=1, hangs=True)
    assert h.serve() == 0
    p = h.started[0]
    assert p.killed
    assert p.waits_after_kill >= 1


# --- port_answers (the one real-network test: a socket bound here) ----------------


def test_port_answers_true_for_a_listening_socket():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        assert block.port_answers("127.0.0.1", port) is True


def test_port_answers_false_for_a_closed_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    assert block.port_answers("127.0.0.1", port) is False


# --- safe ---------------------------------------------------------------------------

SPECIAL = "\\`*_{}[]()#+-.!|~$<>:"


def unescape(text: str) -> str:
    """What Markdown shows: a backslash before any punctuation is dropped."""
    return re.sub(r"\\([^\w\s])", r"\1", text)


@pytest.mark.parametrize("char", list(SPECIAL))
def test_safe_puts_a_backslash_before_each_special_character(char):
    assert block.safe(char) == "\\" + char


def test_safe_escapes_every_special_in_a_row():
    assert block.safe(SPECIAL) == "".join("\\" + c for c in SPECIAL)


def test_safe_leaves_plain_text_unchanged():
    plain = "Rapamycin inhibits mTOR 42 times"
    assert block.safe(plain) == plain


def test_safe_dollar_amount_survives_markdown():
    assert block.safe("$5") == "\\$5"
    assert unescape(block.safe("$5 and $10")) == "$5 and $10"


def test_safe_emoji_code_shows_as_text():
    assert block.safe(":warning:") == r"\:warning\:"
    assert unescape(block.safe(":warning:")) == ":warning:"


def test_safe_windows_path_survives_markdown():
    path = r"C:\Users\me\cards.jsonl"
    assert unescape(block.safe(path)) == path
