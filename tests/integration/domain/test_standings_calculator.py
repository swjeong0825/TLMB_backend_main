"""Unit tests for StandingsCalculator (pure domain logic – no DB required)."""
from __future__ import annotations

import pytest

from app.domain.aggregates.league.entities import Player, Pair
from app.domain.aggregates.league.league_rules import LeagueRules
from app.domain.aggregates.league.value_objects import PlayerId, PlayerNickname, PairId
from app.domain.aggregates.match.aggregate_root import Match
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.aggregates.match.value_objects import MatchId, SetScore
from app.domain.services.standings_calculator import StandingsCalculator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


DEFAULT_RULES = LeagueRules.default_for_new_league()


def make_player(nickname: str) -> Player:
    return Player(player_id=PlayerId.generate(), nickname=PlayerNickname(nickname))


def make_pair(p1: Player, p2: Player) -> Pair:
    pid1, pid2 = p1.player_id, p2.player_id
    if str(pid1.value) > str(pid2.value):
        pid1, pid2 = pid2, pid1
    return Pair(pair_id=PairId.generate(), player_id_1=pid1, player_id_2=pid2)


def make_match(league_id: LeagueId, pair1: Pair, pair2: Pair, t1_score: str, t2_score: str) -> Match:
    return Match.create(league_id, pair1.pair_id, pair2.pair_id, SetScore(t1_score, t2_score))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_empty_matches_returns_zero_wins_for_all_pairs() -> None:
    alice, bob = make_player("alice"), make_player("bob")
    charlie, diana = make_player("charlie"), make_player("diana")
    pair_ab = make_pair(alice, bob)
    pair_cd = make_pair(charlie, diana)
    calculator = StandingsCalculator()

    entries = calculator.compute(
        matches=[], pairs=[pair_ab, pair_cd], players=[alice, bob, charlie, diana], rules=DEFAULT_RULES
    )

    assert len(entries) == 2
    for e in entries:
        assert e.wins == 0
        assert e.losses == 0


def test_pair1_win_increments_wins_and_losses() -> None:
    alice, bob = make_player("alice"), make_player("bob")
    charlie, diana = make_player("charlie"), make_player("diana")
    pair_ab = make_pair(alice, bob)
    pair_cd = make_pair(charlie, diana)
    league_id = LeagueId.generate()

    match = make_match(league_id, pair_ab, pair_cd, t1_score="6", t2_score="3")
    entries = StandingsCalculator().compute(
        [match], [pair_ab, pair_cd], [alice, bob, charlie, diana], DEFAULT_RULES
    )

    ab_entry = next(e for e in entries if e.pair_id == str(pair_ab.pair_id.value))
    cd_entry = next(e for e in entries if e.pair_id == str(pair_cd.pair_id.value))

    assert ab_entry.wins == 1
    assert ab_entry.losses == 0
    assert cd_entry.wins == 0
    assert cd_entry.losses == 1


def test_pair2_win_increments_correctly() -> None:
    alice, bob = make_player("alice"), make_player("bob")
    charlie, diana = make_player("charlie"), make_player("diana")
    pair_ab = make_pair(alice, bob)
    pair_cd = make_pair(charlie, diana)
    league_id = LeagueId.generate()

    match = make_match(league_id, pair_ab, pair_cd, t1_score="2", t2_score="6")
    entries = StandingsCalculator().compute(
        [match], [pair_ab, pair_cd], [alice, bob, charlie, diana], DEFAULT_RULES
    )

    ab_entry = next(e for e in entries if e.pair_id == str(pair_ab.pair_id.value))
    cd_entry = next(e for e in entries if e.pair_id == str(pair_cd.pair_id.value))

    assert ab_entry.wins == 0
    assert ab_entry.losses == 1
    assert cd_entry.wins == 1
    assert cd_entry.losses == 0


def test_draw_not_counted_as_win_or_loss() -> None:
    alice, bob = make_player("alice"), make_player("bob")
    charlie, diana = make_player("charlie"), make_player("diana")
    pair_ab = make_pair(alice, bob)
    pair_cd = make_pair(charlie, diana)
    league_id = LeagueId.generate()

    match = make_match(league_id, pair_ab, pair_cd, t1_score="6", t2_score="6")
    entries = StandingsCalculator().compute(
        [match], [pair_ab, pair_cd], [alice, bob, charlie, diana], DEFAULT_RULES
    )

    for e in entries:
        assert e.wins == 0
        assert e.losses == 0
        assert e.draws == 1
        assert e.matches_played == 1


def test_winner_ranked_first() -> None:
    alice, bob = make_player("alice"), make_player("bob")
    charlie, diana = make_player("charlie"), make_player("diana")
    pair_ab = make_pair(alice, bob)
    pair_cd = make_pair(charlie, diana)
    league_id = LeagueId.generate()

    match = make_match(league_id, pair_ab, pair_cd, "6", "3")
    entries = StandingsCalculator().compute(
        [match], [pair_ab, pair_cd], [alice, bob, charlie, diana], DEFAULT_RULES
    )

    assert entries[0].pair_id == str(pair_ab.pair_id.value)
    assert entries[0].rank == 1
    assert entries[1].rank == 2


def test_tied_pairs_share_same_rank() -> None:
    alice, bob = make_player("alice"), make_player("bob")
    charlie, diana = make_player("charlie"), make_player("diana")
    pair_ab = make_pair(alice, bob)
    pair_cd = make_pair(charlie, diana)
    league_id = LeagueId.generate()

    # Two matches, each pair wins once → tied at 1 win each
    m1 = make_match(league_id, pair_ab, pair_cd, "6", "3")
    m2 = make_match(league_id, pair_cd, pair_ab, "6", "3")
    entries = StandingsCalculator().compute(
        [m1, m2], [pair_ab, pair_cd], [alice, bob, charlie, diana], DEFAULT_RULES
    )

    assert entries[0].wins == 1
    assert entries[1].wins == 1
    assert entries[0].rank == 1
    assert entries[1].rank == 1


def test_accumulated_wins_across_multiple_matches() -> None:
    alice, bob = make_player("alice"), make_player("bob")
    charlie, diana = make_player("charlie"), make_player("diana")
    pair_ab = make_pair(alice, bob)
    pair_cd = make_pair(charlie, diana)
    league_id = LeagueId.generate()

    matches = [
        make_match(league_id, pair_ab, pair_cd, "6", "3"),
        make_match(league_id, pair_ab, pair_cd, "6", "4"),
        make_match(league_id, pair_cd, pair_ab, "6", "1"),
    ]
    entries = StandingsCalculator().compute(
        matches, [pair_ab, pair_cd], [alice, bob, charlie, diana], DEFAULT_RULES
    )

    ab_entry = next(e for e in entries if e.pair_id == str(pair_ab.pair_id.value))
    cd_entry = next(e for e in entries if e.pair_id == str(pair_cd.pair_id.value))

    assert ab_entry.wins == 2
    assert ab_entry.losses == 1
    assert cd_entry.wins == 1
    assert cd_entry.losses == 2


def test_player_nicknames_appear_in_entries() -> None:
    alice, bob = make_player("alice"), make_player("bob")
    charlie, diana = make_player("charlie"), make_player("diana")
    pair_ab = make_pair(alice, bob)
    pair_cd = make_pair(charlie, diana)

    entries = StandingsCalculator().compute(
        [], [pair_ab, pair_cd], [alice, bob, charlie, diana], DEFAULT_RULES
    )

    ab_entry = next(e for e in entries if e.pair_id == str(pair_ab.pair_id.value))
    nicknames = {ab_entry.player1_nickname, ab_entry.player2_nickname}
    assert nicknames == {"alice", "bob"}


def test_empty_pairs_returns_empty_entries() -> None:
    entries = StandingsCalculator().compute([], [], [], DEFAULT_RULES)
    assert entries == []
