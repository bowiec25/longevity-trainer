"""web_launch: Open a Streamlit page on this computer only: start it, wait until it answers, open the browser, stop it cleanly; plus Markdown-safe text for pages

See SPEC.md in this folder (ADR 0003; generic copy of HSK ADR 0014's launcher).
"""

import re
import socket
import subprocess
import sys
import time
import webbrowser
from collections.abc import Callable
from pathlib import Path

from quizkit.blocks.base import BlockSpec

BLOCK_SPEC = BlockSpec(
    name="web_launch",
    kind="script",
    goal="Open a Streamlit page on this computer only: start it, wait until it answers, open the browser, stop it cleanly; plus Markdown-safe text for pages",
    inputs=[
        "page",
        "cwd",
        "host",
        "port",
        "wait",
        "write",
        "open_url",
        "popen",
        "is_up",
        "sleep",
        "text",
    ],
    outputs=["serve", "command", "url", "port_answers", "safe", "HOST", "PORT", "WAIT"],
)

# 127.0.0.1, not "localhost": on Windows a check of "localhost" tries ::1 first and
# waits ~2 s per refused address. Still this computer only.
HOST, PORT = "127.0.0.1", 8501
WAIT = 30.0  # seconds to wait for the page to come up
_CHECK_EVERY = 0.2
_STOP_GRACE = 10  # seconds Streamlit gets to finish after Ctrl-C
_WAIT_STEP = 0.5  # one short wait for the process (Ctrl-C is seen between them)

# Markdown, maths and Streamlit's :emoji: / :material/...: codes: each gets a backslash
_MARKDOWN = re.compile(r"([\\`*_{}\[\]()#+\-.!|~$<>:])")


def safe(text: str) -> str:
    """Text shown as written: Streamlit reads Markdown and maths, so "$5" or a
    Windows path would otherwise be mangled."""
    return _MARKDOWN.sub(r"\\\1", text)


def url(host: str = HOST, port: int = PORT) -> str:
    return f"http://{host}:{port}"


def command(page: Path, host: str = HOST, port: int = PORT) -> list[str]:
    """Local only, headless (no first-run email question), no usage data, no
    Deploy button."""
    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(page),
        f"--server.address={host}",
        f"--server.port={port}",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
        "--client.toolbarMode=minimal",
    ]


def port_answers(host: str, port: int) -> bool:
    """Is something answering on the address?"""
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def _say(write: Callable[[str], None], line: str) -> None:
    if write is print:
        print(line, flush=True)
    else:
        write(line)


def serve(
    page: Path,
    cwd: Path,
    host: str = HOST,
    port: int = PORT,
    wait: float = WAIT,
    write: Callable[[str], None] = print,
    open_url: Callable[[str], object] = webbrowser.open,
    popen: Callable[..., subprocess.Popen] = subprocess.Popen,
    is_up: Callable[[str, int], bool] = port_answers,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Start the page, open it once it answers, and wait; returns an exit code."""
    address = url(host, port)
    if is_up(host, port):  # e.g. a copy left running in another window
        _say(write, f"Something is already running at {address}.")
        _say(write, "If it's the quiz, just open that page; otherwise stop it first.")
        return 1
    process = popen(command(page, host, port), cwd=cwd)
    try:
        if _wait_until_up(process, host, port, wait, is_up, sleep):
            _say(write, f"The quiz is open at {address} (Ctrl-C here stops it).")
            open_url(address)
        elif process.poll() is None:  # still starting after `wait`: say where
            _say(write, f"Streamlit is slow to start: open {address} once it's ready.")
        return _wait(process)
    except KeyboardInterrupt:  # Streamlit gets the Ctrl-C too: let it finish
        _stop(process)
        return 0


def _wait(process: subprocess.Popen) -> int:
    """Wait for the process in short steps: on Windows one endless wait can't be
    interrupted by Ctrl-C, so a hung Streamlit could never be stopped."""
    while True:
        try:
            return process.wait(timeout=_WAIT_STEP)
        except subprocess.TimeoutExpired:
            continue


def _wait_until_up(
    process: subprocess.Popen,
    host: str,
    port: int,
    wait: float,
    is_up: Callable[[str, int], bool],
    sleep: Callable[[float], None],
) -> bool:
    """True once the page answers; False if the process stopped or time ran out."""
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        if is_up(host, port):
            return True
        sleep(_CHECK_EVERY)
    return False


def _stop(process: subprocess.Popen) -> None:
    """After Ctrl-C: give Streamlit time to finish, then kill it (also on a second
    Ctrl-C), so no copy is left holding the address."""
    try:
        process.wait(timeout=_STOP_GRACE)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        process.kill()
        process.wait()
