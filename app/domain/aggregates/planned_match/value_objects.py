from dataclasses import dataclass

from app.domain.exceptions import InvalidPlannedMatchError, InvalidPlayerNicknameError
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
