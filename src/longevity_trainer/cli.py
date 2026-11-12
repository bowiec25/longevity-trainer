"""The terminal front end: `longevity quiz`, `check-receipts` and `check-cards-exam`.

`quiz` plays the cards, with the receipt after each answer.
`check-receipts` finds every card's quote in its pinned source (downloads it if needed).
`check-cards-exam` scores the card checker on the labelled exam (real Claude;
--holdout for the never-tuned-on cards, --limit, --dry-run).

Marking:
- name / fact cards: the quizkit grader (small typos forgiven).
- any answer the answer list calls wrong goes to Claude (the `marking` block):
  word-level for names and facts, main idea for explanations. If Claude can't be
  reached, or with --no-judge, you see the model answer and mark it yourself.
  Claude's "no" is final for now (disputing a verdict is in docs/FUTURE.md).
Progress isn't saved yet.
"""

import argparse
import random
import sys
import textwrap
from collections.abc import Callable

from longevity_trainer.blocks.card_bank import ROOT, LongevityCard, load_cards
from longevity_trainer.blocks.card_checker import (
    EXAM_FILE,
    HOLDOUT_FILE,
    check_card,
    load_exam,
    run_exam,
)
from longevity_trainer.blocks.marking import make_judge
from quizkit.blocks.engine import Attempt, QuizSession
from quizkit.blocks.receipts import check_all
from quizkit.claude import ask_claude
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
    replies = []

    def ask(prompt: str, **kwargs: object) -> object:
        reply = ask_claude(prompt, **kwargs)
        replies.append(reply)
        return reply

    report = run_exam(
        cases, check=lambda card: check_card(card, ask=ask, model=model), model=model
    )
    cost = sum(r.cost_usd or 0 for r in replies)
    tokens = sum(r.input_tokens + r.output_tokens for r in replies)
    print(f"{len(replies)} Claude calls, {tokens} tokens, ${cost:.4f}")
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
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):  # Windows consoles: show ✓ and quotes
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.command == "check-receipts":
        return check_all_receipts()
    if args.command == "check-cards-exam":
        return cards_exam(args.model, args.holdout, args.limit, args.dry_run)
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
