"""Longevity cards: a question, accepted answers, and a receipt (source + quote + page).

Stored one card per line in data/cards/*.jsonl. `to_quizkit` turns them into the
generic quizkit Card, so the engine, grader and progress tracking can be reused.
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from quizkit.models import Card

ROOT = Path(__file__).resolve().parents[2]
CARDS_DIR = ROOT / "data" / "cards"

# Kinds of card (ADR 0005). "explain" and "term" will be marked by the Claude judge.
Kind = Literal["name", "fact", "term", "explain"]


class Receipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str = Field(min_length=1)
    quote: str = Field(min_length=20)
    page: int = Field(ge=1, description="PDF page (1 = first page of the file)")


class LongevityCard(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1)
    kind: Kind
    topic: str = Field(min_length=1)
    question: str = Field(min_length=10)
    answers: list[str] = Field(min_length=1)
    receipt: Receipt

    def to_quizkit(self) -> Card:
        return Card(
            id=self.id,
            fields={"question": self.question, "kind": self.kind, "topic": self.topic},
            answers=self.answers,
            level=1,
        )


def load_cards(cards_dir: Path = CARDS_DIR) -> list[LongevityCard]:
    """Read every card; fail loudly on a bad line or a repeated id."""
    cards: list[LongevityCard] = []
    for path in sorted(cards_dir.glob("*.jsonl")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                try:
                    cards.append(LongevityCard.model_validate_json(line))
                except ValueError as err:
                    raise ValueError(f"{path.name} line {number}: {err}") from err
    ids = [c.id for c in cards]
    repeated = {i for i in ids if ids.count(i) > 1}
    if repeated:
        raise ValueError(f"repeated card ids: {sorted(repeated)}")
    return cards
