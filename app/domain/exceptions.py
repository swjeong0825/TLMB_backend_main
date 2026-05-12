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


class EligiblePlayerNotFoundError(DomainError):
    pass


class EligiblePlayerNicknameAlreadyExistsError(DomainError):
    pass


class IneligiblePlayerError(DomainError):
    """Raised by `League.validate_match_participants_eligible` when match-
    submission nicknames are not present in the league's `eligible_players`
    allowlist.

    `missing_nicknames` is the structured payload (list of normalized
    nicknames) that the API layer surfaces to clients verbatim, so the chat
    server / frontend can render the missing names without re-parsing the
    `detail` string.
    """

    def __init__(self, message: str, missing_nicknames: list[str]) -> None:
        super().__init__(message)
        self.missing_nicknames = missing_nicknames
