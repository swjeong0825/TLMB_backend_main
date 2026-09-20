from dataclasses import dataclass

from app.domain.aggregates.league.value_objects import PlayerNickname
from app.domain.exceptions import (
    InvalidPlannedMatchError,
    InvalidPlayerNicknameError,
    PlannedMatchMismatchError,
)
from app.domain.nicknames import validate_nickname


@dataclass(frozen=True)
class PlannedMatchValue:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise InvalidPlannedMatchError("Planned match value must be a string")
        sides = self.value.split(" ")
        if len(sides) != 2:
            raise InvalidPlannedMatchError("Expected two sides separated by one ASCII space")
        first, second = (side.split(",") for side in sides)
        if len(first) not in (1, 2) or len(first) != len(second):
            raise InvalidPlannedMatchError("Both sides must contain one or two nicknames")
        try:
            for nickname in first + second:
                validate_nickname(nickname, trim=False)
        except InvalidPlayerNicknameError as exc:
            raise InvalidPlannedMatchError(str(exc)) from exc

    def validate_participants(
        self, side1: tuple[str, ...], side2: tuple[str, ...]
    ) -> None:
        """Match normalized names per side, without resolving aliases or swapping sides."""
        planned_sides = [side.split(",") for side in self.value.split(" ")]
        if len(side1) != len(planned_sides[0]) or len(side2) != len(planned_sides[1]):
            raise InvalidPlannedMatchError("Planned match format does not match the result format")
        for submitted, planned in zip((side1, side2), planned_sides):
            if sorted(PlayerNickname(name).value for name in submitted) != sorted(
                PlayerNickname(name).value for name in planned
            ):
                raise PlannedMatchMismatchError("Submitted participants do not match the planned sides")
