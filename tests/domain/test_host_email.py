"""Unit tests for the HostEmail value object.

Format validation (RFC compliance) lives at the API edge in Pydantic's
`EmailStr`; this VO only handles non-blankness and normalization.
"""
from __future__ import annotations

import pytest

from app.domain.aggregates.league.value_objects import HostEmail


class TestHostEmailNormalization:
    def test_stores_lowercased_value(self) -> None:
        email = HostEmail(value="Host@Example.COM")
        assert email.value == "host@example.com"

    def test_strips_surrounding_whitespace(self) -> None:
        email = HostEmail(value="  host@example.com  ")
        assert email.value == "host@example.com"

    def test_strips_then_lowercases(self) -> None:
        email = HostEmail(value="  Host@Example.Com\t")
        assert email.value == "host@example.com"

    def test_value_is_immutable(self) -> None:
        email = HostEmail(value="host@example.com")
        with pytest.raises(Exception):
            email.value = "other@example.com"  # type: ignore[misc]


class TestHostEmailRejection:
    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError):
            HostEmail(value="")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(ValueError):
            HostEmail(value="   ")


class TestHostEmailEquality:
    def test_same_value_equal(self) -> None:
        assert HostEmail(value="host@example.com") == HostEmail(value="host@example.com")

    def test_case_difference_equal_after_normalization(self) -> None:
        assert HostEmail(value="HOST@example.com") == HostEmail(value="host@example.com")

    def test_str_returns_normalized_value(self) -> None:
        assert str(HostEmail(value="Host@Example.com")) == "host@example.com"
