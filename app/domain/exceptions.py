class DomainError(Exception):
    pass


class LeagueNotFoundError(DomainError):
    pass


class PlayerNotFoundError(DomainError):
    pass


class TeamNotFoundError(DomainError):
    pass


class MatchNotFoundError(DomainError):
    pass


class UnauthorizedError(DomainError):
    pass


class LeagueTitleAlreadyExistsError(DomainError):
    pass


class TeamConflictError(DomainError):
    pass


class NicknameAlreadyInUseError(DomainError):
    pass


class TeamHasMatchesError(DomainError):
    pass


class SameTeamOnBothSidesError(DomainError):
    pass


class SamePlayerWithinSingleTeamError(DomainError):
    pass


class SamePlayerOnBothTeamsError(DomainError):
    pass


class InvalidSetScoreError(DomainError):
    pass


class InvalidLeagueRulesError(DomainError):
    pass


class DuplicateTeamPairMatchError(DomainError):
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


class PlayerHasParticipationError(DomainError):
    """Raised by `League.remove_player` when the player is on at least one
    team or referenced by at least one match.

    Carries the participation counts so the API layer can surface a clear
    "X teams, Y matches" message verbatim. Removal is only allowed when both
    counts are zero.
    """

    def __init__(
        self,
        message: str,
        player_id: str,
        teams_count: int,
        matches_count: int,
    ) -> None:
        super().__init__(message)
        self.player_id = player_id
        self.teams_count = teams_count
        self.matches_count = matches_count
