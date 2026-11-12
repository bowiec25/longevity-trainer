"""The terminal front end: `longevity quiz` and `longevity check-receipts`.

`quiz` plays the cards, with the receipt after each answer.
`check-receipts` finds every card's quote in its pinned source (downloads it if needed).

Marking (v1, free and instant):
- name / fact cards: the quizkit grader (small typos forgiven).
- explain / term cards, or any answer the grader calls wrong: you see the model
  answer and mark yourself ("Count it as right? y/n"). The Claude judge comes in M4.
Progress isn't saved yet.
"""

import argparse
import random
import sys
import textwrap
from collections.abc import Callable

from longevity_trainer.blocks.card_bank import ROOT, LongevityCard, load_cards
from quizkit.blocks.engine import Attempt, QuizSession
from quizkit.blocks.receipts import check_all
from quizkit.models import Question, Verdict
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
) -> tuple[int, int]:
    """Ask every card in order; return (right, answered)."""
    by_id = {c.id: c for c in cards}
    session = QuizSession([to_question(c) for c in cards])
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
        if attempt.correct:
            write("   ✓ Right")
        else:
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


def check_all_receipts(write: Callable[[str], None] = print) -> int:
    """Check every card's quote; one line per problem, then a one-line summary."""
    cards = load_cards()
    problems = check_all([(c.id, c.receipt) for c in cards], SOURCES_DIR, ROOT)
    for line in problems:
        write(line)
    write(f"receipts: {len(cards) - len(problems)}/{len(cards)} quotes found")
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="longevity")
    sub = parser.add_subparsers(dest="command", required=True)
    quiz = sub.add_parser("quiz", help="play the cards")
    quiz.add_argument("-n", type=int, default=None, help="how many questions")
    quiz.add_argument("--seed", type=int, default=None, help="fixed order (testing)")
    sub.add_parser("check-receipts", help="find every quote in its pinned source")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):  # Windows consoles: show ✓ and quotes
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.command == "check-receipts":
        return check_all_receipts()
    cards = load_cards()
    random.Random(args.seed).shuffle(cards)
    if args.n is not None:
        cards = cards[: max(1, args.n)]
    try:
        play(cards)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0
