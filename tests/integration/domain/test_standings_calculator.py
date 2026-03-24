"""Unit tests for StandingsCalculator (pure domain logic – no DB required)."""
from __future__ import annotations

import pytest

from app.domain.aggregates.league.entities import Player, Team
from app.domain.aggregates.league.value_objects import PlayerId, PlayerNickname, TeamId
from app.domain.aggregates.match.aggregate_root import Match
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.aggregates.match.value_objects import MatchId, SetScore
from app.domain.services.standings_calculator import StandingsCalculator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_player(nickname: str) -> Player:
    return Player(player_id=PlayerId.generate(), nickname=PlayerNickname(nickname))


def make_team(p1: Player, p2: Player) -> Team:
    pid1, pid2 = p1.player_id, p2.player_id
    if str(pid1.value) > str(pid2.value):
        pid1, pid2 = pid2, pid1
    return Team(team_id=TeamId.generate(), player_id_1=pid1, player_id_2=pid2)


def make_match(league_id: LeagueId, team1: Team, team2: Team, t1_score: str, t2_score: str) -> Match:
    return Match.create(league_id, team1.team_id, team2.team_id, SetScore(t1_score, t2_score))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_empty_matches_returns_zero_wins_for_all_teams() -> None:
    alice, bob = make_player("alice"), make_player("bob")
    charlie, diana = make_player("charlie"), make_player("diana")
    team_ab = make_team(alice, bob)
    team_cd = make_team(charlie, diana)
    calculator = StandingsCalculator()

    entries = calculator.compute(matches=[], teams=[team_ab, team_cd], players=[alice, bob, charlie, diana])

    assert len(entries) == 2
    for e in entries:
        assert e.wins == 0
        assert e.losses == 0


def test_team1_win_increments_wins_and_losses() -> None:
    alice, bob = make_player("alice"), make_player("bob")
    charlie, diana = make_player("charlie"), make_player("diana")
    team_ab = make_team(alice, bob)
    team_cd = make_team(charlie, diana)
    league_id = LeagueId.generate()

    match = make_match(league_id, team_ab, team_cd, t1_score="6", t2_score="3")
    entries = StandingsCalculator().compute([match], [team_ab, team_cd], [alice, bob, charlie, diana])

    ab_entry = next(e for e in entries if e.team_id == str(team_ab.team_id.value))
    cd_entry = next(e for e in entries if e.team_id == str(team_cd.team_id.value))

    assert ab_entry.wins == 1
    assert ab_entry.losses == 0
    assert cd_entry.wins == 0
    assert cd_entry.losses == 1


def test_team2_win_increments_correctly() -> None:
    alice, bob = make_player("alice"), make_player("bob")
    charlie, diana = make_player("charlie"), make_player("diana")
    team_ab = make_team(alice, bob)
    team_cd = make_team(charlie, diana)
    league_id = LeagueId.generate()

    match = make_match(league_id, team_ab, team_cd, t1_score="2", t2_score="6")
    entries = StandingsCalculator().compute([match], [team_ab, team_cd], [alice, bob, charlie, diana])

    ab_entry = next(e for e in entries if e.team_id == str(team_ab.team_id.value))
    cd_entry = next(e for e in entries if e.team_id == str(team_cd.team_id.value))

    assert ab_entry.wins == 0
    assert ab_entry.losses == 1
    assert cd_entry.wins == 1
    assert cd_entry.losses == 0


def test_draw_not_counted_as_win_or_loss() -> None:
    alice, bob = make_player("alice"), make_player("bob")
    charlie, diana = make_player("charlie"), make_player("diana")
    team_ab = make_team(alice, bob)
    team_cd = make_team(charlie, diana)
    league_id = LeagueId.generate()

    match = make_match(league_id, team_ab, team_cd, t1_score="6", t2_score="6")
    entries = StandingsCalculator().compute([match], [team_ab, team_cd], [alice, bob, charlie, diana])

    for e in entries:
        assert e.wins == 0
        assert e.losses == 0


def test_winner_ranked_first() -> None:
    alice, bob = make_player("alice"), make_player("bob")
    charlie, diana = make_player("charlie"), make_player("diana")
    team_ab = make_team(alice, bob)
    team_cd = make_team(charlie, diana)
    league_id = LeagueId.generate()

    match = make_match(league_id, team_ab, team_cd, "6", "3")
    entries = StandingsCalculator().compute([match], [team_ab, team_cd], [alice, bob, charlie, diana])

    assert entries[0].team_id == str(team_ab.team_id.value)
    assert entries[0].rank == 1
    assert entries[1].rank == 2


def test_tied_teams_share_same_rank() -> None:
    alice, bob = make_player("alice"), make_player("bob")
    charlie, diana = make_player("charlie"), make_player("diana")
    team_ab = make_team(alice, bob)
    team_cd = make_team(charlie, diana)
    league_id = LeagueId.generate()

    # Two matches, each team wins once → tied at 1 win each
    m1 = make_match(league_id, team_ab, team_cd, "6", "3")
    m2 = make_match(league_id, team_cd, team_ab, "6", "3")
    entries = StandingsCalculator().compute([m1, m2], [team_ab, team_cd], [alice, bob, charlie, diana])

    assert entries[0].wins == 1
    assert entries[1].wins == 1
    assert entries[0].rank == 1
    assert entries[1].rank == 1


def test_accumulated_wins_across_multiple_matches() -> None:
    alice, bob = make_player("alice"), make_player("bob")
    charlie, diana = make_player("charlie"), make_player("diana")
    team_ab = make_team(alice, bob)
    team_cd = make_team(charlie, diana)
    league_id = LeagueId.generate()

    matches = [
        make_match(league_id, team_ab, team_cd, "6", "3"),
        make_match(league_id, team_ab, team_cd, "6", "4"),
        make_match(league_id, team_cd, team_ab, "6", "1"),
    ]
    entries = StandingsCalculator().compute(matches, [team_ab, team_cd], [alice, bob, charlie, diana])

    ab_entry = next(e for e in entries if e.team_id == str(team_ab.team_id.value))
    cd_entry = next(e for e in entries if e.team_id == str(team_cd.team_id.value))

    assert ab_entry.wins == 2
    assert ab_entry.losses == 1
    assert cd_entry.wins == 1
    assert cd_entry.losses == 2


def test_player_nicknames_appear_in_entries() -> None:
    alice, bob = make_player("alice"), make_player("bob")
    charlie, diana = make_player("charlie"), make_player("diana")
    team_ab = make_team(alice, bob)
    team_cd = make_team(charlie, diana)

    entries = StandingsCalculator().compute([], [team_ab, team_cd], [alice, bob, charlie, diana])

    ab_entry = next(e for e in entries if e.team_id == str(team_ab.team_id.value))
    nicknames = {ab_entry.player1_nickname, ab_entry.player2_nickname}
    assert nicknames == {"alice", "bob"}


def test_empty_teams_returns_empty_entries() -> None:
    entries = StandingsCalculator().compute([], [], [])
    assert entries == []
