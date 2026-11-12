"""The terminal front end: `longevity quiz`, `check-receipts` and `check-cards-exam`.

`quiz` plays the cards, with the receipt after each answer.
`check-receipts` finds every card's quote in its pinned source (downloads it if needed).
`check-cards-exam` scores the card checker on the labelled exam (real Claude;
--holdout for the never-tuned-on cards, --limit, --dry-run).
`write-cards` drafts cards on a topic from a pinned source, gates them (quote found,
no repeats, card checker) and saves the survivors to data/cards/<topic>.jsonl.

Marking:
- name / fact cards: the quizkit grader (small typos forgiven).
- any answer the answer list calls wrong goes to Claude (the `marking` block):
  word-level for names and facts, main idea for explanations. If Claude can't be
  reached, or with --no-judge, you see the model answer and mark it yourself.
  Claude's "no" is final for now (disputing a verdict is in docs/FUTURE.md).
Progress isn't saved yet.
"""

import argparse
import os
import random
import sys
import tempfile
import textwrap
from collections.abc import Callable
from pathlib import Path

from longevity_trainer.blocks.card_bank import (
    CARDS_DIR,
    ROOT,
    LongevityCard,
    load_cards,
)
from longevity_trainer.blocks.card_checker import (
    EXAM_FILE,
    HOLDOUT_FILE,
    check_card,
    load_exam,
    run_exam,
)
from longevity_trainer.blocks.card_writer import (
    ASKS,
    REQUIRED_ASKS,
    slug,
    write_cards,
)
from longevity_trainer.blocks.marking import make_judge
from quizkit.blocks.engine import Attempt, QuizSession
from quizkit.blocks.receipts import check_all
from quizkit.claude import ClaudeError, ask_claude
from quizkit.download import DownloadError
from quizkit.models import Judge, Question, Verdict
from quizkit.modes import Mode, build_question

SELF_YES = Verdict(correct=True, reason="you marked it right", source="self")
SELF_NO = Verdict(correct=False, reason="you marked it wrong", source="self")
QUIT_WORDS = {"q", "quit", "exit"}

Read = Callable[[str], str | None]  # shows a prompt, returns the line (None = end)


def _read(prompt: str) -> str | None:
    try:
        return input(prompt)
    except EOFError:
        return None


def to_question(card: LongevityCard) -> Question:
    """The card as a question; its kind (name, fact, term, explain) is the mode, so
    saved progress and the judge can tell kinds apart."""
    return build_question(card.to_quizkit(), Mode(name=card.kind, show=["question"]))


def _wrap(text: str, indent: str = "   ") -> str:
    return textwrap.fill(
        text, width=88, initial_indent=indent, subsequent_indent=indent
    )


def _ask_yes_no(read: Read, prompt: str) -> bool | None:
    while True:
        reply = read(prompt)
        if reply is None:
            return None
        reply = reply.strip().lower()
        if reply in ("y", "yes"):
            return True
        if reply in ("n", "no"):
            return False


def play(
    cards: list[LongevityCard],
    read: Read = _read,
    write: Callable[[str], None] = print,
    judge: Judge | None = None,
) -> tuple[int, int]:
    """Ask every card in order; return (right, answered).

    With a `judge`, Claude marks any answer the answer list calls wrong; if Claude
    can't be reached, you mark it yourself."""
    by_id = {c.id: c for c in cards}

    session = QuizSession([to_question(c) for c in cards], judge=judge)
    write(f"Longevity quiz: {len(cards)} questions. Type q to stop.\n")
    number = 0
    while not session.done:
        number += 1
        card = by_id[session.current.card_id]
        write(textwrap.fill(f"{number}. {card.question}", 88, subsequent_indent="   "))
        typed = read("   > ")
        if typed is None or typed.strip().lower() in QUIT_WORDS:
            break
        attempt: Attempt = session.answer(typed)
        verdict = attempt.verdict
        checked = verdict is not None and verdict.source != "not_checked"
        if attempt.correct:
            write(
                _wrap(f"✓ Right (Claude: {verdict.reason})")
                if checked
                else "   ✓ Right"
            )
            if checked:
                write(_wrap(f"Model answer: {card.answers[0]}"))
        else:
            if checked:
                write(_wrap(f"✗ Claude: {verdict.reason}"))
            elif verdict is not None:  # Claude couldn't check
                write(_wrap(f"(Claude: {verdict.reason})"))
            write(_wrap(f"Answer: {card.answers[0]}"))
            if typed.strip() and session.can_own_mark:
                mark = _ask_yes_no(read, "   Count it as right? (y/n) ")
                if mark is None:
                    break
                session.own_mark(SELF_YES if mark else SELF_NO, card_id=card.id)
                write("   ✓ Counted" if mark else "   ✗ Not this time")
            else:
                write("   ✗ Not this time")
        r = card.receipt
        write(_wrap(f'Receipt: "{r.quote}" ({r.source}, p. {r.page})') + "\n")
    result = session.result()
    write(f"Score: {result.correct} / {result.answered}")
    return result.correct, result.answered


SOURCES_DIR = ROOT / "data" / "sources"
JUDGE_CACHE = ROOT / "data" / "judge_cache.jsonl"  # gitignored: your answers


def check_all_receipts(write: Callable[[str], None] = print) -> int:
    """Check every card's quote; one line per problem, then a one-line summary."""
    cards = load_cards()
    problems = check_all([(c.id, c.receipt) for c in cards], SOURCES_DIR, ROOT)
    for line in problems:
        write(line)
    write(f"receipts: {len(cards) - len(problems)}/{len(cards)} quotes found")
    return 1 if problems else 0


def _counting_ask() -> tuple[Callable[..., object], list]:
    """ask_claude that keeps every reply, for the calls / tokens / cost line."""
    replies: list = []

    def ask(prompt: str, **kwargs: object) -> object:
        reply = ask_claude(prompt, **kwargs)
        replies.append(reply)
        return reply

    return ask, replies


def _cost_line(replies: list) -> str:
    cost = sum(r.cost_usd or 0 for r in replies)
    tokens = sum(r.input_tokens + r.output_tokens for r in replies)
    return f"{len(replies)} Claude calls, {tokens} tokens, ${cost:.4f}"


def _load_texts(texts: dict[str, str]) -> list[LongevityCard]:
    """Cards from {file name: file text}, through the shared loader (which reads a
    folder). No cards = empty; a bad line or repeated id raises ValueError."""
    if not texts:
        return []
    with tempfile.TemporaryDirectory() as tmp:
        for name, text in texts.items():
            (Path(tmp) / name).write_text(text, "utf-8", newline="")
        try:
            return load_cards(Path(tmp))
        except ValueError as err:
            if str(err).startswith("no cards found"):  # only blank files
                return []
            raise


def _bank(
    out: Path, with_topic: bool
) -> tuple[list[LongevityCard], str | None, list[str]]:
    """(cards in the bank, the topic file's text or None, its card ids), reading each file
    once. The topic file `out` counts only `with_topic` (--add, or a dry run);
    otherwise it's not read, so a broken one can still be replaced."""
    texts = {
        p.name: p.read_text("utf-8-sig")
        for p in sorted(CARDS_DIR.glob("*.jsonl"))
        if p.is_file() and (with_topic or p != out)
    }
    topic_text = texts.get(out.name) if with_topic else None
    bank = _load_texts(texts)
    topic_ids = [c.id for c in _load_texts({out.name: topic_text or ""})]
    return bank, topic_text, topic_ids


def _coverage(topic_slug: str, ids: list[str]) -> str:
    """Which asks a topic's cards cover (read from ids `<slug>-<ask>-<k>`)."""
    found = set()
    for card_id in ids:
        rest = card_id.removeprefix(f"{topic_slug}-")
        ask = rest.rpartition("-")[0].replace("-", "_")
        if rest != card_id and ask in ASKS:
            found.add(ask)
    covered = [a for a in ASKS if a in found]
    missing = [a for a in ASKS if a in REQUIRED_ASKS and a not in found]
    line = f"topic {topic_slug} covers: {', '.join(covered) or 'nothing yet'}; "
    if missing:
        return line + f"missing: {', '.join(missing)} (run again with --add)"
    return line + "nothing missing"


def _page_range(text: str) -> tuple[int, int]:
    """`--pages 17-20` -> (17, 20); `--pages 5` -> (5, 5)."""
    first, dash, last = text.partition("-")
    try:
        pages = (int(first), int(last) if dash else int(first))
    except ValueError:
        pages = (0, 0)
    if pages[0] < 1 or pages[1] < pages[0]:
        raise argparse.ArgumentTypeError(f"{text!r}: use A-B (e.g. 17-20) or one page")
    return pages


def write_cards_command(
    topic: str,
    source: str,
    n: int,
    model: str,
    dry_run: bool,
    replace: bool,
    write: Callable[[str], None] = print,
    pages: tuple[int, int] | None = None,
    add: bool = False,
) -> int:
    """Draft, gate and (unless --dry-run) save cards; exit code 0 = the bar is met."""
    out = CARDS_DIR / f"{slug(topic)}.jsonl"
    if out.exists() and not (replace or add or dry_run):
        write(
            f"{out.name} already exists: use --add to add cards to it, "
            "or --replace to overwrite it"
        )
        return 1
    with_topic = add or (dry_run and not replace)
    try:
        bank, old, topic_ids = _bank(out, with_topic)
    except ValueError as err:  # bad line, repeated id, not UTF-8: ids could clash
        write(f"the card bank has a problem, fix it first: {str(err).splitlines()[0]}")
        return 1
    ask, replies = _counting_ask()
    try:
        result = write_cards(
            topic,
            source,
            n=n,
            model=model,
            taken_ids={c.id for c in bank},
            taken_questions={c.question for c in bank},
            pages=pages,
            ask=ask,
            check=lambda card: check_card(card, ask=ask),
        )
    except (OSError, ValueError, DownloadError, ClaudeError) as err:
        write(str(err).splitlines()[0])
        return 1
    for card in result.kept:
        write(_wrap(f"✓ {card.id}: {card.question} → {card.answers[0]}"))
    for drop in result.drops:
        write(_wrap(f"✗ {drop.gate}: {drop.question} ({drop.reason})"))
    r = result.report
    write(
        f"\n{r.model} (prompt v{r.prompt_version}): kept {r.kept}/{r.drafted}; "
        f"dropped shape {r.dropped_shape}, quote {r.dropped_quote}, "
        f"repeat {r.dropped_repeat}, checker {r.dropped_checker}; "
        f"asks kept {r.asks_kept} -> {'PASSED' if r.passed else 'NOT PASSED'}"
    )
    write(_cost_line(replies))
    ok = r.passed and bool(result.kept)
    new_ids = [c.id for c in result.kept] if ok else []
    coverage = _coverage(slug(topic), topic_ids + new_ids)
    if not ok:
        write(coverage)
        write("nothing written")
        return 1
    if dry_run:
        write(coverage)
        write("dry run: nothing written")
        return 0
    now = out.read_text("utf-8-sig") if out.exists() else None
    if not replace and now != old:  # old: the text read before the run (None = no file)
        write(f"{out.name} changed during the run (another run or an edit): run again")
        return 1
    old = old or ""
    if old and not old.endswith("\n"):
        old += "\n"
    try:  # write a temp file, then swap it in: a failed write keeps the old cards
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.name + ".tmp")
        tmp.write_text(
            old + "".join(card.model_dump_json() + "\n" for card in result.kept),
            "utf-8",
            newline="\n",
        )
        os.replace(tmp, out)
    except OSError as err:
        write(f"couldn't write {out.name}: {err}")
        return 1
    write(coverage)
    write(f"wrote {len(result.kept)} cards to {out}")
    return 0


def cards_exam(model: str, holdout: bool, limit: int | None, dry_run: bool) -> int:
    """Score the card checker on the exam; exit code 0 = the bar is met."""
    try:
        cases = load_exam(HOLDOUT_FILE if holdout else EXAM_FILE)
    except ValueError as err:
        print(err)
        return 1
    if limit is not None:
        cases = cases[: max(1, limit)]
    if dry_run:
        for case in cases:
            print(f"{case.id}: expected {case.expected} {case.rules or ''}".rstrip())
        print(f"{len(cases)} cards; no Claude calls (dry run)")
        return 0
    ask, replies = _counting_ask()
    report = run_exam(
        cases, check=lambda card: check_card(card, ask=ask, model=model), model=model
    )
    print(_cost_line(replies))
    return 0 if report.passed else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="longevity")
    sub = parser.add_subparsers(dest="command", required=True)
    quiz = sub.add_parser("quiz", help="play the cards")
    quiz.add_argument("-n", type=int, default=None, help="how many questions")
    quiz.add_argument("--seed", type=int, default=None, help="fixed order (testing)")
    quiz.add_argument(
        "--no-judge", action="store_true", help="mark open answers yourself, no Claude"
    )
    sub.add_parser("check-receipts", help="find every quote in its pinned source")
    exam = sub.add_parser(
        "check-cards-exam",
        help="score the card checker on the labelled exam (real Claude)",
    )
    exam.add_argument("--model", default="haiku", help="Claude model (haiku, sonnet…)")
    exam.add_argument(
        "--holdout", action="store_true", help="the held-out cards (never tuned on)"
    )
    exam.add_argument("--limit", type=int, default=None, help="only the first N cards")
    exam.add_argument(
        "--dry-run", action="store_true", help="list the cards; don't call Claude"
    )
    writer = sub.add_parser(
        "write-cards", help="draft cards on a topic from a pinned source (real Claude)"
    )
    writer.add_argument("--topic", required=True, help='e.g. "rapamycin"')
    writer.add_argument("--source", required=True, help="source id in data/sources")
    writer.add_argument("--n", type=int, default=8, help="cards to draft (1-20)")
    writer.add_argument("--model", default="sonnet", help="the writer's Claude model")
    writer.add_argument(
        "--pages", type=_page_range, default=None, help="only these pages, e.g. 17-20"
    )
    writer.add_argument(
        "--dry-run", action="store_true", help="draft and gate, but write nothing"
    )
    grow = writer.add_mutually_exclusive_group()
    grow.add_argument(
        "--add", action="store_true", help="add cards to the topic's card file"
    )
    grow.add_argument(
        "--replace", action="store_true", help="overwrite the topic's card file"
    )
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):  # Windows consoles: show ✓ and quotes
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.command == "check-receipts":
        return check_all_receipts()
    if args.command == "check-cards-exam":
        return cards_exam(args.model, args.holdout, args.limit, args.dry_run)
    if args.command == "write-cards":
        return write_cards_command(
            args.topic,
            args.source,
            args.n,
            args.model,
            args.dry_run,
            args.replace,
            pages=args.pages,
            add=args.add,
        )
    cards = load_cards()
    random.Random(args.seed).shuffle(cards)
    if args.n is not None:
        cards = cards[: max(1, args.n)]
    judge = None
    if not args.no_judge:
        judge = make_judge(
            cache_file=JUDGE_CACHE,
            before_asking=lambda: print("   asking Claude…", flush=True),
        )
    try:
        play(cards, judge=judge)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0
