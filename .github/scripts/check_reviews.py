"""CI check: the PR description must show the build loop's reviews were done.

The loop (CLAUDE.md "Workflow"): SPEC -> test-writer -> build -> block-reviewer +
/code-review -> PR. Under "## Reviews", each of the three must be either ticked
("- [x] test-writer ...") or marked "n/a: <reason>" (e.g. "n/a: docs only, no code").
Like the other PR check, it proves the box was ticked, not that the review was good;
the GitHub Claude review and the block reviewer's report in the PR are the evidence.
"""

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from check_pr_body import answer_of, sections

HEADING = "## Reviews"
ITEMS = ("test-writer", "block-reviewer", "/code-review")
MIN_REASON = 10  # "n/a: docs only" passes; "n/a" alone doesn't
# "- [x] test-writer ..." or "- [ ] test-writer n/a: reason": the item comes first
LINE = re.compile(r"\s*[-*]\s*\[(?P<tick>[ xX])\]\s*(?P<item>\S+)(?P<rest>.*)")


def is_reviews_heading(line: str) -> bool:
    title = line.strip().lstrip("#").strip().lower()
    return line.strip().startswith("#") and title.startswith("reviews")


def item_ok(match: re.Match) -> bool:
    if match["tick"] in "xX":
        return True
    na = re.search(r"\bn/a\b\s*:?\s*(.*)", match["rest"], re.IGNORECASE)
    return bool(na) and len(na.group(1).strip()) >= MIN_REASON


def check(body: str) -> str | None:
    """None if the body passes, otherwise the reason it fails."""
    found = sections(body, is_heading=is_reviews_heading)
    if not found:
        return f'The PR description has no "{HEADING}" section.'
    lines = "\n".join(answer_of(text) for text in found).split("\n")
    matches = [m for m in map(LINE.match, lines) if m]
    for item in ITEMS:
        mine = [m for m in matches if m["item"].lower().rstrip(":") == item]
        if not mine:
            return f'"{HEADING}" has no checkbox line starting with {item}.'
        if not any(item_ok(m) for m in mine):
            return f'{item} is not done: tick it ("- [x]") or write "n/a: <reason>".'
    return None


def main() -> int:
    problem = check(os.environ.get("PR_BODY", ""))
    if problem:
        print(f"::error::{problem}")
        return 1
    print("Reviews section: test-writer, block-reviewer and /code-review all done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
