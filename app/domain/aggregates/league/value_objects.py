from __future__ import annotations

import uuid
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domain.exceptions import InvalidLeagueRulesError
from app.domain.nicknames import NICKNAME_WHITESPACE, validate_nickname


DEFAULT_LEAGUE_TIMEZONE = "America/Los_Angeles"


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
class LeagueTimezone:
    """IANA timezone used for league-local calendar-day boundaries."""

    value: str = DEFAULT_LEAGUE_TIMEZONE

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise InvalidLeagueRulesError(
                "league_timezone must be a non-empty IANA timezone string"
            )
        normalized = self.value.strip()
        try:
            ZoneInfo(normalized)
        except ZoneInfoNotFoundError as exc:
            raise InvalidLeagueRulesError(
                f"Invalid league_timezone: {normalized!r}; expected an IANA timezone"
            ) from exc
        object.__setattr__(self, "value", normalized)

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
        object.__setattr__(self, "value", validate_nickname(self.value).lower())

    @classmethod
    def from_persisted(cls, value: str) -> PlayerNickname:
        """Restore a stored name verbatim, including names predating the grammar."""
        nickname = object.__new__(cls)
        object.__setattr__(nickname, "value", value)
        return nickname

    @classmethod
    def for_lookup(cls, value: str) -> PlayerNickname:
        """Use historical normalization for identifying, never writing, names."""
        return cls.from_persisted(value.lower().strip())

    @classmethod
    def lookup_candidates(cls, value: str) -> tuple[PlayerNickname, ...]:
        """Prefer an exact stored name, then current and historical trimming.

        ECMAScript and Python disagree about BOM and U+0085, so neither trim
        convention alone can identify every old and newly valid nickname.
        """
        lowered = value.lower()
        values = dict.fromkeys((lowered, lowered.strip(NICKNAME_WHITESPACE), lowered.strip()))
        return tuple(cls.from_persisted(candidate) for candidate in values)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class PairId:
    value: uuid.UUID

    @classmethod
    def generate(cls) -> PairId:
        return cls(value=uuid.uuid4())

    @classmethod
    def from_str(cls, s: str) -> PairId:
        return cls(value=uuid.UUID(s))

    def __str__(self) -> str:
        return str(self.value)
