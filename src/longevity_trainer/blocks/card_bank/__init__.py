"""card_bank: Load the longevity cards (question, answers, receipt) from data/cards and turn them into quizkit cards.

See SPEC.md in this folder (ADR 0003).
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from quizkit.blocks.base import BlockSpec
from quizkit.blocks.jsonl_loader import load_jsonl_dir
from quizkit.blocks.receipts import Receipt
from quizkit.models import Card

BLOCK_SPEC = BlockSpec(
    name="card_bank",
    kind="script",
    goal="Load the longevity cards (question, answers, receipt) from data/cards and turn them into quizkit cards.",
    inputs=["cards_dir"],
    outputs=["LongevityCard", "load_cards", "to_quizkit", "ROOT", "CARDS_DIR"],
)

ROOT = Path(__file__).resolve().parents[4]
CARDS_DIR = ROOT / "data" / "cards"

# Kinds of card (ADR 0005). "term" and "explain" will be marked by the Claude judge.
Kind = Literal["name", "fact", "term", "explain"]


class LongevityCard(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    id: str = Field(min_length=1)
    kind: Kind
    topic: str = Field(min_length=1)
    question: str = Field(min_length=10)
    answers: list[str] = Field(min_length=1)
    receipt: Receipt

    @field_validator("kind", mode="before")
    @classmethod
    def strip_kind(cls, kind: object) -> object:
        return (
            kind.strip() if isinstance(kind, str) else kind
        )  # a Literal isn't stripped

    @field_validator("answers")
    @classmethod
    def no_blank_answers(cls, answers: list[str]) -> list[str]:
        if any(not a for a in answers):  # already stripped
            raise ValueError("answers must not be blank")
        return answers

    def to_quizkit(self) -> Card:
        return Card(
            id=self.id,
            fields={"question": self.question, "kind": self.kind, "topic": self.topic},
            answers=self.answers,
            level=1,
        )


def load_cards(cards_dir: Path = CARDS_DIR) -> list[LongevityCard]:
    """Every card, in file then line order; a bad line or repeated id fails loudly."""
    return load_jsonl_dir(cards_dir, LongevityCard, what="cards")
