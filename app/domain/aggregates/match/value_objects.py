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
    team1_score: str
    team2_score: str

    def __post_init__(self) -> None:
        self._validate_score(self.team1_score)
        self._validate_score(self.team2_score)

    @staticmethod
    def _validate_score(score: str) -> None:
        try:
            val = int(score)
        except (ValueError, TypeError):
            raise InvalidSetScoreError(f"Score '{score}' is not a valid integer")
        if val < 0:
            raise InvalidSetScoreError(f"Score '{score}' must be a non-negative integer")

    def winner_side(self) -> str:
        t1 = int(self.team1_score)
        t2 = int(self.team2_score)
        if t1 > t2:
            return "team1"
        if t2 > t1:
            return "team2"
        return "draw"
