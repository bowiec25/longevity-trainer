# Block: `web_launch`

> **In plain words:** Open a Streamlit page on this computer only: start it, wait until it answers, open the browser, stop it cleanly; plus Markdown-safe text for pages

## Goal
Open a Streamlit page on this computer only: start it, wait until it answers, open the browser, stop it cleanly. Plus Markdown-safe text for pages.

It exists because every quiz with a web page needs the same careful launcher: local only, no usage data sent, no first-run email prompt, no copy left holding the port after Ctrl-C. It also needs the same text escaping, because Streamlit reads text as Markdown and maths, so "$5" or a Windows path would be mangled. HSK wrote both inside its `cli.py` (HSK ADR 0014); this is the generic copy (longevity ADR 0009), and it will be ported back to HSK. It knows nothing about any quiz: the caller passes the page file and the folder.

**Not in scope:** what the page shows; installing Streamlit (a project dependency); hosting online.

## Kind
**script.** Whether the page answers on its address, and what command was run, are checkable by code.

## Inputs
| Input | Type | Plain meaning |
|---|---|---|
| `page` | `Path` | The Streamlit script to run (e.g. the quiz's `web_app.py`) |
| `cwd` | `Path` | The folder Streamlit runs in, so it finds `.streamlit/config.toml` (the project root) |
| `host`, `port` | `str`, `int` | Default `HOST = "127.0.0.1"` (not "localhost": on Windows that tries `::1` first and waits ~2 s per refused address), `PORT = 8501` |
| `wait` | `float` | Seconds to wait for the page to come up, by the real clock (default `WAIT = 30.0`); the process stopping is checked before the address each round |
| `write` | `Callable[[str], None]` | Where messages go (default `print`, flushed) |
| `open_url` | `Callable[[str], object]` | Opens the browser (default `webbrowser.open`) |
| `popen` | callable | Starts the process, called as `popen(command, cwd=cwd)` (default `subprocess.Popen`; tests pass a fake) |
| `is_up` | `Callable[[str, int], bool]` | Is something answering on the address? (default: a TCP connect with a 0.5 s timeout) |
| `sleep` | `Callable[[float], None]` | Pause between checks (default `time.sleep`; tests pass a no-op) |
| `text` | `str` | For `safe`: text to show as written |

**How it's called** (importable from `quizkit.blocks.web_launch`):
```python
code = serve(page, cwd)  # blocks until Streamlit stops; returns an exit code
st.markdown(safe(reason))  # in a page
```

## Outputs
| Output | Type | Plain meaning |
|---|---|---|
| `serve(page, cwd, host=HOST, port=PORT, wait=WAIT, write=print, open_url=webbrowser.open, popen=subprocess.Popen, is_up=port_answers, sleep=time.sleep)` | `int` (exit code) | 1. If something already answers at the address: writes `"Something is already running at <url>."` and `"If it's the quiz, just open that page; otherwise stop it first."`, starts nothing, returns 1. 2. Starts `command(page, host, port)` with `cwd`. 3. Checks `is_up` every 0.2 s (via `sleep`) until it answers (writes `"The quiz is open at <url> (Ctrl-C here stops it)."` and calls `open_url(url)` once), or the process stops (opens nothing), or `wait` seconds pass with it still running (writes `"Streamlit is slow to start: open <url> once it's ready."`, opens nothing). 4. Waits for the process and returns its exit code, **in short waits** (`process.wait(timeout=0.5)`, again on `subprocess.TimeoutExpired`), because on Windows one endless wait can't be interrupted by Ctrl-C. **Ctrl-C** while waiting: gives Streamlit 10 s to finish (it gets the Ctrl-C too), then kills it (also on a second Ctrl-C or if it hangs); returns 0, never a traceback |
| `command(page, host=HOST, port=PORT)` | `list[str]` | `[sys.executable, "-m", "streamlit", "run", str(page), "--server.address=<host>", "--server.port=<port>", "--server.headless=true", "--browser.gatherUsageStats=false", "--client.toolbarMode=minimal"]`: this computer only, no first-run email question (it crashed without a keyboard), no usage data, no Deploy button |
| `url(host=HOST, port=PORT)` | `str` | `"http://<host>:<port>"` |
| `port_answers(host, port)` | `bool` | True if a TCP connection to the address succeeds within 0.5 s |
| `safe(text)` | `str` | Each Markdown or maths character `` \ ` * _ { } [ ] ( ) # + - . ! \| ~ $ < > `` and `:` (Streamlit's `:emoji:` and `:material/...:` codes) gets a backslash in front, so Streamlit shows the text as written |
| `HOST`, `PORT`, `WAIT` | constants | `"127.0.0.1"`, `8501`, `30.0` |

Nothing is written to disk.

## Tools
- `subprocess`, `socket`, `time`, `webbrowser`, `sys` (standard library)
- `re` (for `safe`)

## Failure modes
| Situation | What it does |
|---|---|
| The port is already taken (another copy, or another program) | The two lines above, nothing started, returns 1 |
| Streamlit stops before the page answers (e.g. a crash) | Opens nothing; returns Streamlit's exit code |
| Streamlit is still starting after `wait` seconds | The "slow to start" line; keeps waiting for the process; opens nothing |
| Ctrl-C once (while starting up or after) | Streamlit finishes by itself (not killed); returns 0 whatever Streamlit's own code |
| Ctrl-C twice, or Streamlit hangs more than 10 s after Ctrl-C | Killed, then waited for, so nothing is left holding the port; returns 0 |
| `streamlit` not installed | Streamlit's own error from the process, and its exit code (it's a project dependency, so this means a broken install) |

## How to test
Automatic tests in `tests/blocks/test_web_launch.py`, with a **fake process** (`poll`, `wait`, `kill`), a fake `is_up` (a list of answers), a no-op `sleep`, and a list as `open_url`. The real Streamlit is never started and the network is never used.
- **command:** starts with `[sys.executable, "-m", "streamlit", "run", page]`; has each local-only flag; the port is the one given
- **serve:** starts it with `cwd`, opens the URL once, and returns 0; when something's already there, nothing starts and it returns 1 with the message; a process that stops early opens nothing and returns its code; slow start says where and opens nothing (with `wait=0`); Ctrl-C once means not killed and 0; twice, or hanging after Ctrl-C, means killed and 0
- **url:** `http://127.0.0.1:8501` by default
- **port_answers:** True for a real listening socket on 127.0.0.1 (bound by the test, port 0), False for a closed port
- **safe:** each special character gets a backslash; plain text is unchanged; "$5" and a Windows path survive once Markdown unescapes them
- **Contract test:** folder parts exist and `BLOCK_SPEC` matches this SPEC
