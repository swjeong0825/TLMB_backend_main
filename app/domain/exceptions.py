class DomainError(Exception):
    pass


class LeagueNotFoundError(DomainError):
    pass


class PlayerNotFoundError(DomainError):
    pass


class PairNotFoundError(DomainError):
    pass


class MatchNotFoundError(DomainError):
    pass


class UnauthorizedError(DomainError):
    pass


class LeagueTitleAlreadyExistsError(DomainError):
    pass


class PairConflictError(DomainError):
    pass


class NicknameAlreadyInUseError(DomainError):
    pass


class LastNicknameError(DomainError):
    def __init__(self, message: str, player_id: str) -> None:
        super().__init__(message)
        self.player_id = player_id


class CannotRemoveCanonicalNicknameError(DomainError):
    def __init__(
        self,
        message: str,
        player_id: str,
        canonical_nickname: str,
    ) -> None:
        super().__init__(message)
        self.player_id = player_id
        self.canonical_nickname = canonical_nickname


class PairHasMatchesError(DomainError):
    pass


class SamePairOnBothSidesError(DomainError):
    pass


class SamePlayerWithinSinglePairError(DomainError):
    pass


class SamePlayerOnBothPairsError(DomainError):
    pass


class SamePlayerOnBothSidesError(DomainError):
    pass


class InvalidSetScoreError(DomainError):
    pass


class InvalidLeagueRulesError(DomainError):
    pass


class InvalidPlayerRatingError(DomainError):
    pass


class DuplicatePairMatchupMatchError(DomainError):
    pass


class RosterMembershipRequiredError(DomainError):
    """Raised by `League.validate_match_participants_on_roster` when match
    submission contains a nickname not present on the league's roster and
    `LeagueRules.auto_register_players_on_match` is `False`.

    `missing_nicknames` is the structured payload (list of normalized
    nicknames) that the API layer surfaces to clients verbatim, so the chat
    server / frontend can render the missing names without re-parsing the
    `detail` string.
    """

    def __init__(self, message: str, missing_nicknames: list[str]) -> None:
        super().__init__(message)
        self.missing_nicknames = missing_nicknames


class MatchEditWindowExpiredError(DomainError):
    """Raised by `EditMatchScoreUseCase` when a non-admin caller tries to
    edit a match whose `created_at` is older than the configured
    player-edit window.

    Carries the structured fields the frontend needs to render a precise
    "this match can no longer be edited (try the host)" message without
    re-parsing the human-readable `detail` string:

    - `match_id`: the match the caller tried to edit.
    - `window_seconds`: the configured window length, so the UI can echo
      "for the first N minutes after submission".
    - `age_seconds`: how old the match was when the request arrived,
      computed at the use case to avoid clock skew across layers.

    Maps to HTTP 422 (structural / domain rule violation, not auth) so it
    sits alongside `InvalidSetScoreError` and the other 422-mapped
    domain errors in `app/main.py`.
    """

    def __init__(
        self,
        message: str,
        match_id: str,
        window_seconds: int,
        age_seconds: int,
    ) -> None:
        super().__init__(message)
        self.match_id = match_id
        self.window_seconds = window_seconds
        self.age_seconds = age_seconds


class MatchDeleteWindowExpiredError(DomainError):
    """Raised by `DeleteMatchUseCase` when a non-admin caller tries to
    delete a match whose `created_at` is older than the configured
    player-delete window.

    Mirrors `MatchEditWindowExpiredError` in shape and intent: the
    fields below let the frontend render a precise "this match can no
    longer be deleted (ask the host)" message without re-parsing the
    human-readable `detail` string. A distinct class (rather than
    reusing the edit error) lets the UI localise the two messages
    independently and lets ops grep logs by operation kind.

    - `match_id`: the match the caller tried to delete.
    - `window_seconds`: the configured delete window length, so the UI
      can echo "for the first N minutes after submission".
    - `age_seconds`: how old the match was when the request arrived.

    Maps to HTTP 422, alongside `MatchEditWindowExpiredError`, in
    `app/main.py`.
    """

    def __init__(
        self,
        message: str,
        match_id: str,
        window_seconds: int,
        age_seconds: int,
    ) -> None:
        super().__init__(message)
        self.match_id = match_id
        self.window_seconds = window_seconds
        self.age_seconds = age_seconds


class PlayerHasParticipationError(DomainError):
    """Raised by `League.remove_player` when the player is on at least one
    pair or referenced by at least one match.

    Carries the participation counts so the API layer can surface a clear
    "X pairs, Y matches" message verbatim. Removal is only allowed when both
    counts are zero.
    """

    def __init__(
        self,
        message: str,
        player_id: str,
        pairs_count: int,
        matches_count: int,
    ) -> None:
        super().__init__(message)
        self.player_id = player_id
        self.pairs_count = pairs_count
        self.matches_count = matches_count
