from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.domain.exceptions import InvalidSetScoreError


@dataclass(frozen=True)
class MatchId:
    value: uuid.UUID

    @classmethod
    def generate(cls) -> MatchId:
        return cls(value=uuid.uuid4())

    @classmethod
    def from_str(cls, s: str) -> MatchId:
        return cls(value=uuid.UUID(s))

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class SetScore:
    pair1_score: str
    pair2_score: str

    def __post_init__(self) -> None:
        self._validate_score(self.pair1_score)
        self._validate_score(self.pair2_score)

    @staticmethod
    def _validate_score(score: str) -> None:
        try:
            val = int(score)
        except (ValueError, TypeError):
            raise InvalidSetScoreError(f"Score '{score}' is not a valid integer")
        if val < 0:
            raise InvalidSetScoreError(f"Score '{score}' must be a non-negative integer")

    def winner_side(self) -> str:
        pair1_score = int(self.pair1_score)
        pair2_score = int(self.pair2_score)
        if pair1_score > pair2_score:
            return "pair1"
        if pair2_score > pair1_score:
            return "pair2"
        return "draw"
