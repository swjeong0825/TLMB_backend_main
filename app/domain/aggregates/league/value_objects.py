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
class HostEmail:
    """Host contact email, normalized to stripped lowercase.

    Format validation is performed at the API edge by Pydantic's
    `EmailStr`; this VO is a typed wrapper that ensures non-blankness
    and applies the same case-normalization other text VOs use
    (mirroring `PlayerNickname`). Immutable after league creation in V1
    — no admin endpoint mutates it.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise ValueError("HostEmail cannot be empty")
        object.__setattr__(self, "value", self.value.strip().lower())

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
