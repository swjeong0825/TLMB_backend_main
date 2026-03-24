"""Unit tests for StandingsCalculator domain service.

Focused on edge cases and multi-team scenarios not fully covered by the
integration-level standings tests.
"""
from __future__ import annotations

import pytest

from app.domain.aggregates.league.entities import Player, Team
from app.domain.aggregates.league.value_objects import LeagueId, PlayerId, PlayerNickname, TeamId
from app.domain.aggregates.match.aggregate_root import Match
from app.domain.aggregates.match.value_objects import SetScore
from app.domain.services.standings_calculator import StandingsCalculator, StandingsEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _player(nickname: str) -> Player:
    return Player(player_id=PlayerId.generate(), nickname=PlayerNickname(nickname))


def _team(p1: Player, p2: Player) -> Team:
    pid1, pid2 = p1.player_id, p2.player_id
    if str(pid1.value) > str(pid2.value):
        pid1, pid2 = pid2, pid1
    return Team(team_id=TeamId.generate(), player_id_1=pid1, player_id_2=pid2)


def _match(league_id: LeagueId, t1: Team, t2: Team, s1: str, s2: str) -> Match:
    return Match.create(league_id, t1.team_id, t2.team_id, SetScore(s1, s2))


LEAGUE = LeagueId.generate()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStandingsCalculatorBasic:
    def test_no_teams_returns_empty_list(self) -> None:
        entries = StandingsCalculator().compute([], [], [])
        assert entries == []

    def test_no_matches_all_teams_have_zero_record(self) -> None:
        alice, bob = _player("alice"), _player("bob")
        charlie, diana = _player("charlie"), _player("diana")
        team_ab = _team(alice, bob)
        team_cd = _team(charlie, diana)
        entries = StandingsCalculator().compute(
            [], [team_ab, team_cd], [alice, bob, charlie, diana]
        )
        for e in entries:
            assert e.wins == 0
            assert e.losses == 0

    def test_single_match_team1_wins(self) -> None:
        alice, bob = _player("alice"), _player("bob")
        charlie, diana = _player("charlie"), _player("diana")
        team_ab = _team(alice, bob)
        team_cd = _team(charlie, diana)
        m = _match(LEAGUE, team_ab, team_cd, "6", "3")

        entries = StandingsCalculator().compute(
            [m], [team_ab, team_cd], [alice, bob, charlie, diana]
        )
        ab = next(e for e in entries if e.team_id == str(team_ab.team_id.value))
        cd = next(e for e in entries if e.team_id == str(team_cd.team_id.value))

        assert ab.wins == 1 and ab.losses == 0
        assert cd.wins == 0 and cd.losses == 1

    def test_single_match_team2_wins(self) -> None:
        alice, bob = _player("alice"), _player("bob")
        charlie, diana = _player("charlie"), _player("diana")
        team_ab = _team(alice, bob)
        team_cd = _team(charlie, diana)
        m = _match(LEAGUE, team_ab, team_cd, "2", "6")

        entries = StandingsCalculator().compute(
            [m], [team_ab, team_cd], [alice, bob, charlie, diana]
        )
        ab = next(e for e in entries if e.team_id == str(team_ab.team_id.value))
        cd = next(e for e in entries if e.team_id == str(team_cd.team_id.value))

        assert ab.wins == 0 and ab.losses == 1
        assert cd.wins == 1 and cd.losses == 0

    def test_draw_does_not_add_wins_or_losses(self) -> None:
        alice, bob = _player("alice"), _player("bob")
        charlie, diana = _player("charlie"), _player("diana")
        team_ab = _team(alice, bob)
        team_cd = _team(charlie, diana)
        m = _match(LEAGUE, team_ab, team_cd, "6", "6")

        entries = StandingsCalculator().compute(
            [m], [team_ab, team_cd], [alice, bob, charlie, diana]
        )
        for e in entries:
            assert e.wins == 0
            assert e.losses == 0


class TestStandingsRanking:
    def test_winner_ranked_above_loser(self) -> None:
        alice, bob = _player("alice"), _player("bob")
        charlie, diana = _player("charlie"), _player("diana")
        team_ab = _team(alice, bob)
        team_cd = _team(charlie, diana)
        m = _match(LEAGUE, team_ab, team_cd, "6", "3")

        entries = StandingsCalculator().compute(
            [m], [team_ab, team_cd], [alice, bob, charlie, diana]
        )
        assert entries[0].rank == 1
        assert entries[1].rank == 2
        assert entries[0].team_id == str(team_ab.team_id.value)

    def test_tied_teams_share_rank_1(self) -> None:
        alice, bob = _player("alice"), _player("bob")
        charlie, diana = _player("charlie"), _player("diana")
        team_ab = _team(alice, bob)
        team_cd = _team(charlie, diana)
        m1 = _match(LEAGUE, team_ab, team_cd, "6", "3")
        m2 = _match(LEAGUE, team_cd, team_ab, "6", "3")

        entries = StandingsCalculator().compute(
            [m1, m2], [team_ab, team_cd], [alice, bob, charlie, diana]
        )
        assert entries[0].wins == 1
        assert entries[1].wins == 1
        assert entries[0].rank == 1
        assert entries[1].rank == 1

    def test_three_teams_ranks_assigned_correctly(self) -> None:
        alice, bob = _player("alice"), _player("bob")
        charlie, diana = _player("charlie"), _player("diana")
        eve, frank = _player("eve"), _player("frank")
        team_ab = _team(alice, bob)
        team_cd = _team(charlie, diana)
        team_ef = _team(eve, frank)

        m1 = _match(LEAGUE, team_ab, team_cd, "6", "3")
        m2 = _match(LEAGUE, team_ab, team_ef, "6", "2")

        entries = StandingsCalculator().compute(
            [m1, m2],
            [team_ab, team_cd, team_ef],
            [alice, bob, charlie, diana, eve, frank],
        )
        ab = next(e for e in entries if e.team_id == str(team_ab.team_id.value))
        assert ab.rank == 1
        assert ab.wins == 2

        losers = [e for e in entries if e.wins == 0]
        assert all(e.rank == 2 for e in losers)


class TestStandingsNicknames:
    def test_player_nicknames_present_in_entry(self) -> None:
        alice, bob = _player("alice"), _player("bob")
        team_ab = _team(alice, bob)

        entries = StandingsCalculator().compute([], [team_ab], [alice, bob])
        assert len(entries) == 1
        nicknames = {entries[0].player1_nickname, entries[0].player2_nickname}
        assert nicknames == {"alice", "bob"}

    def test_unknown_player_id_shows_unknown(self) -> None:
        alice, bob = _player("alice"), _player("bob")
        team_ab = _team(alice, bob)
        entries = StandingsCalculator().compute([], [team_ab], [])
        assert entries[0].player1_nickname == "unknown"
        assert entries[0].player2_nickname == "unknown"


class TestStandingsAccumulation:
    def test_multiple_matches_accumulate_correctly(self) -> None:
        alice, bob = _player("alice"), _player("bob")
        charlie, diana = _player("charlie"), _player("diana")
        team_ab = _team(alice, bob)
        team_cd = _team(charlie, diana)

        matches = [
            _match(LEAGUE, team_ab, team_cd, "6", "3"),
            _match(LEAGUE, team_ab, team_cd, "6", "4"),
            _match(LEAGUE, team_cd, team_ab, "6", "1"),
        ]
        entries = StandingsCalculator().compute(
            matches, [team_ab, team_cd], [alice, bob, charlie, diana]
        )
        ab = next(e for e in entries if e.team_id == str(team_ab.team_id.value))
        cd = next(e for e in entries if e.team_id == str(team_cd.team_id.value))

        assert ab.wins == 2 and ab.losses == 1
        assert cd.wins == 1 and cd.losses == 2

    def test_team_with_only_losses_has_zero_wins(self) -> None:
        alice, bob = _player("alice"), _player("bob")
        charlie, diana = _player("charlie"), _player("diana")
        team_ab = _team(alice, bob)
        team_cd = _team(charlie, diana)

        matches = [
            _match(LEAGUE, team_cd, team_ab, "6", "0"),
            _match(LEAGUE, team_cd, team_ab, "6", "1"),
        ]
        entries = StandingsCalculator().compute(
            matches, [team_ab, team_cd], [alice, bob, charlie, diana]
        )
        ab = next(e for e in entries if e.team_id == str(team_ab.team_id.value))
        assert ab.wins == 0
        assert ab.losses == 2
