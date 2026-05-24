"""Process-wide runtime config read from environment variables.

This module is intentionally tiny: the existing codebase reaches for
`os.getenv` directly at the few places that need a knob
(`app/infrastructure/config/database.py`, `app/rate_limit.py`). New
config values that are read from more than one place go here so the
defaults and env-var names live in exactly one location.

Functions (rather than module-level constants) so tests can override
behaviour with `monkeypatch.setenv(...)` without re-importing the
module.
"""

from __future__ import annotations

import os


# Default = 3600s (1h). Players can edit a match's score for this long
# after the match was first recorded; admins (X-Host-Token) bypass the
# window entirely.
_DEFAULT_PLAYER_SCORE_EDIT_WINDOW_SECONDS = 3600

# Default = 600s (10 min). Players can delete a match they just
# recorded for this long after `created_at`; admins (X-Host-Token)
# bypass the window entirely. Deletes are irreversible, so the
# default is tighter than the score-edit window.
_DEFAULT_PLAYER_MATCH_DELETE_WINDOW_SECONDS = 600


def player_score_edit_window_seconds() -> int:
    """Player-edit window in seconds.

    Read from `PLAYER_SCORE_EDIT_WINDOW_SECONDS`; falls back to 3600.
    Non-integer / negative values fall back to the default so a bad
    deployment value can never silently disable the entire feature.
    """
    raw = os.getenv("PLAYER_SCORE_EDIT_WINDOW_SECONDS")
    if raw is None or raw == "":
        return _DEFAULT_PLAYER_SCORE_EDIT_WINDOW_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_PLAYER_SCORE_EDIT_WINDOW_SECONDS
    if value < 0:
        return _DEFAULT_PLAYER_SCORE_EDIT_WINDOW_SECONDS
    return value


def player_match_delete_window_seconds() -> int:
    """Player match-delete window in seconds.

    Read from `PLAYER_MATCH_DELETE_WINDOW_SECONDS`; falls back to 600
    (10 min). Non-integer / negative values fall back to the default
    so a bad deployment value can never silently disable the gate.
    Mirrors `player_score_edit_window_seconds` so the two policies can
    be tuned independently.
    """
    raw = os.getenv("PLAYER_MATCH_DELETE_WINDOW_SECONDS")
    if raw is None or raw == "":
        return _DEFAULT_PLAYER_MATCH_DELETE_WINDOW_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_PLAYER_MATCH_DELETE_WINDOW_SECONDS
    if value < 0:
        return _DEFAULT_PLAYER_MATCH_DELETE_WINDOW_SECONDS
    return value
