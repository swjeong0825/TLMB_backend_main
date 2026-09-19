"""Shared nickname grammar, using the ECMAScript whitespace set."""

from app.domain.exceptions import InvalidPlayerNicknameError


# JavaScript /[\s,]/u and String.trim(), including BOM but excluding U+0085.
NICKNAME_WHITESPACE = (
    "\u0009\u000a\u000b\u000c\u000d\u0020\u00a0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000\ufeff"
)
_FORBIDDEN = frozenset(NICKNAME_WHITESPACE + ",")


def validate_nickname(value: str, *, trim: bool = True) -> str:
    """Validate without changing case or stripping invalid internal characters."""
    if not isinstance(value, str):
        raise InvalidPlayerNicknameError("PlayerNickname must be a string")
    normalized = value.strip(NICKNAME_WHITESPACE) if trim else value
    if not normalized:
        raise InvalidPlayerNicknameError("PlayerNickname cannot be empty")
    if any(char in _FORBIDDEN for char in normalized):
        raise InvalidPlayerNicknameError("PlayerNickname cannot contain whitespace or commas")
    return normalized
