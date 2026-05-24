from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class LeagueId:
    value: uuid.UUID

    @classmethod
    def generate(cls) -> LeagueId:
        return cls(value=uuid.uuid4())

    @classmethod
    def from_str(cls, s: str) -> LeagueId:
        return cls(value=uuid.UUID(s))

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class HostToken:
    value: str

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class PlayerId:
    value: uuid.UUID

    @classmethod
    def generate(cls) -> PlayerId:
        return cls(value=uuid.uuid4())

    @classmethod
    def from_str(cls, s: str) -> PlayerId:
        return cls(value=uuid.UUID(s))

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True)
class PlayerNickname:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("PlayerNickname cannot be empty")
        object.__setattr__(self, "value", self.value.lower().strip())

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class TeamId:
    value: uuid.UUID

    @classmethod
    def generate(cls) -> TeamId:
        return cls(value=uuid.uuid4())

    @classmethod
    def from_str(cls, s: str) -> TeamId:
        return cls(value=uuid.UUID(s))

    def __str__(self) -> str:
        return str(self.value)
