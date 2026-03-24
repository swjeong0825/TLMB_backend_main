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
