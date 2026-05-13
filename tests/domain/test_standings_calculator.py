"""Unit tests for StandingsCalculator domain service.

Covers ranking under both `ranking_subject` values (team and player) and a
range of `tie_breakers` configurations.
"""
from __future__ import annotations

import pytest

from app.domain.aggregates.league.entities import Player, Team
from app.domain.aggregates.league.league_rules import LeagueRules, RankingMetric
from app.domain.aggregates.league.value_objects import (
    LeagueId,
    PlayerId,
    PlayerNickname,
    TeamId,
)
from app.domain.aggregates.match.aggregate_root import Match
from app.domain.aggregates.match.value_objects import SetScore
from app.domain.services.standings_calculator import StandingsCalculator


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


def _rules(
    *,
    ranking_subject: str = "team",
    tie_breakers: tuple[RankingMetric, ...] = ("matches_won",),
    one_team_per_player: bool = True,
) -> LeagueRules:
    return LeagueRules(
        version=5,
        match_pair_idempotency="once_per_league",
        one_team_per_player=one_team_per_player,
        ranking_subject=ranking_subject,  # type: ignore[arg-type]
        tie_breakers=tie_breakers,
        require_allowlist=False,
    )


LEAGUE = LeagueId.generate()
DEFAULT_RULES = _rules()


# ---------------------------------------------------------------------------
# Backwards-compatible behavior: subject="team", tie_breakers=("matches_won",)
# These tests mirror v1 behavior to confirm the v2 default reproduces it.
# ---------------------------------------------------------------------------


class TestStandingsCalculatorBasic:
    def test_no_teams_returns_empty_list(self) -> None:
        entries = StandingsCalculator().compute([], [], [], DEFAULT_RULES)
        assert entries == []

    def test_no_matches_all_teams_have_zero_record(self) -> None:
        alice, bob = _player("alice"), _player("bob")
        charlie, diana = _player("charlie"), _player("diana")
        team_ab = _team(alice, bob)
        team_cd = _team(charlie, diana)
        entries = StandingsCalculator().compute(
            [], [team_ab, team_cd], [alice, bob, charlie, diana], DEFAULT_RULES
        )
        for e in entries:
            assert e.subject_kind == "team"
            assert e.wins == 0
            assert e.losses == 0
            assert e.matches_played == 0

    def test_single_match_team1_wins(self) -> None:
        alice, bob = _player("alice"), _player("bob")
        charlie, diana = _player("charlie"), _player("diana")
        team_ab = _team(alice, bob)
        team_cd = _team(charlie, diana)
        m = _match(LEAGUE, team_ab, team_cd, "6", "3")

        entries = StandingsCalculator().compute(
            [m], [team_ab, team_cd], [alice, bob, charlie, diana], DEFAULT_RULES
        )
        ab = next(e for e in entries if e.team_id == str(team_ab.team_id.value))
        cd = next(e for e in entries if e.team_id == str(team_cd.team_id.value))

        assert ab.wins == 1 and ab.losses == 0
        assert ab.games_won == 6 and ab.games_lost == 3
        assert cd.wins == 0 and cd.losses == 1
        assert cd.games_won == 3 and cd.games_lost == 6

    def test_draw_does_not_add_wins_or_losses_but_counts_matches_played(self) -> None:
        alice, bob = _player("alice"), _player("bob")
        charlie, diana = _player("charlie"), _player("diana")
        team_ab = _team(alice, bob)
        team_cd = _team(charlie, diana)
        m = _match(LEAGUE, team_ab, team_cd, "6", "6")

        entries = StandingsCalculator().compute(
            [m], [team_ab, team_cd], [alice, bob, charlie, diana], DEFAULT_RULES
        )
        for e in entries:
            assert e.wins == 0
            assert e.losses == 0
            assert e.matches_played == 1
            assert e.games_won == 6
            assert e.games_lost == 6


class TestStandingsRanking:
    def test_winner_ranked_above_loser(self) -> None:
        alice, bob = _player("alice"), _player("bob")
        charlie, diana = _player("charlie"), _player("diana")
        team_ab = _team(alice, bob)
        team_cd = _team(charlie, diana)
        m = _match(LEAGUE, team_ab, team_cd, "6", "3")

        entries = StandingsCalculator().compute(
            [m], [team_ab, team_cd], [alice, bob, charlie, diana], DEFAULT_RULES
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
            [m1, m2], [team_ab, team_cd], [alice, bob, charlie, diana], DEFAULT_RULES
        )
        assert entries[0].wins == 1
        assert entries[1].wins == 1
        assert entries[0].rank == 1
        assert entries[1].rank == 1


class TestStandingsNicknames:
    def test_player_nicknames_present_in_entry(self) -> None:
        alice, bob = _player("alice"), _player("bob")
        team_ab = _team(alice, bob)

        entries = StandingsCalculator().compute(
            [], [team_ab], [alice, bob], DEFAULT_RULES
        )
        assert len(entries) == 1
        nicknames = {entries[0].player1_nickname, entries[0].player2_nickname}
        assert nicknames == {"alice", "bob"}

    def test_unknown_player_id_shows_unknown(self) -> None:
        alice, bob = _player("alice"), _player("bob")
        team_ab = _team(alice, bob)
        entries = StandingsCalculator().compute([], [team_ab], [], DEFAULT_RULES)
        assert entries[0].player1_nickname == "unknown"
        assert entries[0].player2_nickname == "unknown"


# ---------------------------------------------------------------------------
# Tie-breaker tests: subject="team"
# ---------------------------------------------------------------------------


class TestTieBreakersTeam:
    def test_secondary_metric_breaks_primary_tie(self) -> None:
        # Three teams, two tied on matches_won (1) but with different games_diff.
        alice, bob = _player("alice"), _player("bob")
        charlie, diana = _player("charlie"), _player("diana")
        eve, frank = _player("eve"), _player("frank")
        team_ab = _team(alice, bob)
        team_cd = _team(charlie, diana)
        team_ef = _team(eve, frank)

        # team_ab beats team_cd 6-1 (huge margin)
        # team_cd beats team_ef 6-2
        # team_ab vs team_ef: 1-6 (ab loses)
        # Records: ab 1W-1L diff=+5-5=0; cd 1W-1L diff=-5+4=-1; ef 1W-1L diff=-4+5=+1
        # Wait: let me recompute carefully.
        # m1 ab vs cd 6-1 -> ab: gw=6, gl=1, diff=+5; cd: gw=1, gl=6, diff=-5
        # m2 cd vs ef 6-2 -> cd: gw=1+6=7, gl=6+2=8, diff=-1; ef: gw=2, gl=6, diff=-4
        # m3 ab vs ef 1-6 -> ab: gw=6+1=7, gl=1+6=7, diff=0; ef: gw=2+6=8, gl=6+1=7, diff=+1
        # All: 1W-1L. Diff order: ef=+1 > ab=0 > cd=-1.
        m1 = _match(LEAGUE, team_ab, team_cd, "6", "1")
        m2 = _match(LEAGUE, team_cd, team_ef, "6", "2")
        m3 = _match(LEAGUE, team_ab, team_ef, "1", "6")

        rules = _rules(tie_breakers=("matches_won", "games_diff"))
        entries = StandingsCalculator().compute(
            [m1, m2, m3],
            [team_ab, team_cd, team_ef],
            [alice, bob, charlie, diana, eve, frank],
            rules,
        )
        ranks_by_team = {e.team_id: e.rank for e in entries}
        assert ranks_by_team[str(team_ef.team_id.value)] == 1
        assert ranks_by_team[str(team_ab.team_id.value)] == 2
        assert ranks_by_team[str(team_cd.team_id.value)] == 3

    def test_full_tuple_tie_shares_rank(self) -> None:
        # Two teams identical on every metric -> share rank 1.
        alice, bob = _player("alice"), _player("bob")
        charlie, diana = _player("charlie"), _player("diana")
        team_ab = _team(alice, bob)
        team_cd = _team(charlie, diana)

        m1 = _match(LEAGUE, team_ab, team_cd, "6", "3")
        m2 = _match(LEAGUE, team_cd, team_ab, "6", "3")

        rules = _rules(tie_breakers=("matches_won", "games_diff", "games_won"))
        entries = StandingsCalculator().compute(
            [m1, m2], [team_ab, team_cd], [alice, bob, charlie, diana], rules
        )
        assert entries[0].rank == 1
        assert entries[1].rank == 1

    def test_games_lost_metric_lower_is_better(self) -> None:
        # Two teams both 1W-1L; team A lost fewer games.
        alice, bob = _player("alice"), _player("bob")
        charlie, diana = _player("charlie"), _player("diana")
        team_ab = _team(alice, bob)
        team_cd = _team(charlie, diana)

        # m1: ab beats cd 6-0  -> ab gw=6 gl=0; cd gw=0 gl=6
        # m2: cd beats ab 6-5  -> ab gw=11 gl=6; cd gw=6 gl=11
        # ab gl=6, cd gl=11. games_lost lower=better => ab ranked first.
        m1 = _match(LEAGUE, team_ab, team_cd, "6", "0")
        m2 = _match(LEAGUE, team_cd, team_ab, "6", "5")

        rules = _rules(tie_breakers=("matches_won", "games_lost"))
        entries = StandingsCalculator().compute(
            [m1, m2], [team_ab, team_cd], [alice, bob, charlie, diana], rules
        )
        assert entries[0].team_id == str(team_ab.team_id.value)
        assert entries[1].team_id == str(team_cd.team_id.value)

    def test_win_pct_metric(self) -> None:
        # Team A: 1 win in 1 match (100%)
        # Team B: 2 wins in 4 matches (50%)
        # Team C: 0 wins in 0 matches (0% by definition).
        alice, bob = _player("alice"), _player("bob")
        charlie, diana = _player("charlie"), _player("diana")
        eve, frank = _player("eve"), _player("frank")
        team_ab = _team(alice, bob)
        team_cd = _team(charlie, diana)
        team_ef = _team(eve, frank)

        m1 = _match(LEAGUE, team_ab, team_cd, "6", "3")
        m2 = _match(LEAGUE, team_cd, team_ab, "0", "0")  # draw, both played
        # Just kidding — drawing doesn't reset wins. Let me redo:
        # We want clean fractions. Use distinct match sets.
        # team_cd plays 4 matches: 2W, 2L vs ef.
        m_cd_ef_1 = _match(LEAGUE, team_cd, team_ef, "6", "2")
        m_cd_ef_2 = _match(LEAGUE, team_cd, team_ef, "6", "1")
        m_ef_cd_1 = _match(LEAGUE, team_ef, team_cd, "6", "3")
        m_ef_cd_2 = _match(LEAGUE, team_ef, team_cd, "6", "4")

        rules = _rules(tie_breakers=("win_pct",))
        entries = StandingsCalculator().compute(
            [m1, m_cd_ef_1, m_cd_ef_2, m_ef_cd_1, m_ef_cd_2],
            [team_ab, team_cd, team_ef],
            [alice, bob, charlie, diana, eve, frank],
            rules,
        )
        # team_ab: 1/1 = 1.0; team_cd: 2/5 = 0.4; team_ef: 2/4 = 0.5
        ranks = {e.team_id: e.rank for e in entries}
        assert ranks[str(team_ab.team_id.value)] == 1
        assert ranks[str(team_ef.team_id.value)] == 2
        assert ranks[str(team_cd.team_id.value)] == 3

    def test_unplayed_team_has_win_pct_zero(self) -> None:
        alice, bob = _player("alice"), _player("bob")
        team_ab = _team(alice, bob)
        rules = _rules(tie_breakers=("win_pct",))
        entries = StandingsCalculator().compute([], [team_ab], [alice, bob], rules)
        assert entries[0].win_pct == 0.0
        assert entries[0].matches_played == 0


# ---------------------------------------------------------------------------
# Tie-breaker tests: subject="player"
# When teammates always partner together, each team's two players share
# identical metric tuples (the v2 equivalence case). v3 cross-rule rejects
# `(player, OTPP=true)` at the input boundary, but these tests construct
# LeagueRules directly to exercise the algorithm's player-subject branch on
# the equivalence case; the rotated-partner case below covers OTPP=false.
# ---------------------------------------------------------------------------


class TestPlayerSubjectRanking:
    def test_player_rows_match_team_rows_when_partners_are_fixed(self) -> None:
        alice, bob = _player("alice"), _player("bob")
        charlie, diana = _player("charlie"), _player("diana")
        eve, frank = _player("eve"), _player("frank")
        team_ab = _team(alice, bob)
        team_cd = _team(charlie, diana)
        team_ef = _team(eve, frank)

        m1 = _match(LEAGUE, team_ab, team_cd, "6", "3")
        m2 = _match(LEAGUE, team_ab, team_ef, "6", "2")
        m3 = _match(LEAGUE, team_cd, team_ef, "6", "4")
        matches = [m1, m2, m3]
        teams = [team_ab, team_cd, team_ef]
        players = [alice, bob, charlie, diana, eve, frank]

        team_rules = _rules(
            ranking_subject="team", tie_breakers=("matches_won", "games_diff")
        )
        player_rules = _rules(
            ranking_subject="player", tie_breakers=("matches_won", "games_diff")
        )

        team_entries = StandingsCalculator().compute(
            matches, teams, players, team_rules
        )
        player_entries = StandingsCalculator().compute(
            matches, teams, players, player_rules
        )

        # 6 player rows, 3 team rows.
        assert len(player_entries) == 6
        assert len(team_entries) == 3

        # Each team's metric tuple should be present twice in player rows.
        for te in team_entries:
            partners = [
                pe for pe in player_entries
                if pe.wins == te.wins
                and pe.losses == te.losses
                and pe.games_won == te.games_won
                and pe.games_lost == te.games_lost
            ]
            assert len(partners) == 2

    def test_fixed_partners_share_rank(self) -> None:
        alice, bob = _player("alice"), _player("bob")
        charlie, diana = _player("charlie"), _player("diana")
        team_ab = _team(alice, bob)
        team_cd = _team(charlie, diana)
        m = _match(LEAGUE, team_ab, team_cd, "6", "3")

        rules = _rules(ranking_subject="player")
        entries = StandingsCalculator().compute(
            [m], [team_ab, team_cd], [alice, bob, charlie, diana], rules
        )
        ranks_by_nickname = {e.nickname: e.rank for e in entries}
        assert ranks_by_nickname["alice"] == ranks_by_nickname["bob"] == 1
        assert ranks_by_nickname["charlie"] == ranks_by_nickname["diana"] == 3

    def test_player_subject_emits_player_id_and_nickname(self) -> None:
        alice, bob = _player("alice"), _player("bob")
        team_ab = _team(alice, bob)
        rules = _rules(ranking_subject="player")
        entries = StandingsCalculator().compute([], [team_ab], [alice, bob], rules)
        for e in entries:
            assert e.subject_kind == "player"
            assert e.player_id is not None
            assert e.nickname in {"alice", "bob"}
            assert e.team_id is None
            assert e.player1_nickname is None


# ---------------------------------------------------------------------------
# v3 worked example: rotated partners under (player, OTPP=false)
# Source: backend_main/Design_Doc/TLMB_Design_doc/18_configurable_ranking_v3.md
# §"Worked example: distinct player rows under OTPP=false".
# ---------------------------------------------------------------------------


class TestPlayerSubjectOTPPFalse:
    def test_rotated_partners_produce_distinct_player_rows(self) -> None:
        alice = _player("alice")
        bob = _player("bob")
        charlie = _player("charlie")
        dan = _player("dan")

        team_ab = _team(alice, bob)
        team_cd = _team(charlie, dan)
        team_ac = _team(alice, charlie)
        team_bd = _team(bob, dan)
        team_bc = _team(bob, charlie)
        team_ad = _team(alice, dan)

        # Match 1: Alice+Bob 6-4 Charlie+Dan
        # Match 2: Alice+Charlie 6-2 Bob+Dan
        # Match 3: Bob+Charlie 6-3 Alice+Dan
        m1 = _match(LEAGUE, team_ab, team_cd, "6", "4")
        m2 = _match(LEAGUE, team_ac, team_bd, "6", "2")
        m3 = _match(LEAGUE, team_bc, team_ad, "6", "3")

        rules = _rules(
            ranking_subject="player",
            one_team_per_player=False,
            tie_breakers=("matches_won", "games_diff"),
        )

        entries = StandingsCalculator().compute(
            [m1, m2, m3],
            [team_ab, team_cd, team_ac, team_bd, team_bc, team_ad],
            [alice, bob, charlie, dan],
            rules,
        )

        by_nick = {e.nickname: e for e in entries}

        # Alice: matches 1 (W 6-4), 2 (W 6-2), 3 (L 3-6) -> 2W 1L, gw=15 gl=12 diff=+3
        assert by_nick["alice"].wins == 2
        assert by_nick["alice"].losses == 1
        assert by_nick["alice"].games_won == 15
        assert by_nick["alice"].games_lost == 12
        assert by_nick["alice"].games_diff == 3

        # Bob: matches 1 (W 6-4), 2 (L 2-6), 3 (W 6-3) -> 2W 1L, gw=14 gl=13 diff=+1
        assert by_nick["bob"].wins == 2
        assert by_nick["bob"].losses == 1
        assert by_nick["bob"].games_won == 14
        assert by_nick["bob"].games_lost == 13
        assert by_nick["bob"].games_diff == 1

        # Charlie: matches 1 (L 4-6), 2 (W 6-2), 3 (W 6-3) -> 2W 1L, gw=16 gl=11 diff=+5
        assert by_nick["charlie"].wins == 2
        assert by_nick["charlie"].losses == 1
        assert by_nick["charlie"].games_won == 16
        assert by_nick["charlie"].games_lost == 11
        assert by_nick["charlie"].games_diff == 5

        # Dan: matches 1 (L 4-6), 2 (L 2-6), 3 (L 3-6) -> 0W 3L, gw=9 gl=18 diff=-9
        assert by_nick["dan"].wins == 0
        assert by_nick["dan"].losses == 3
        assert by_nick["dan"].games_won == 9
        assert by_nick["dan"].games_lost == 18
        assert by_nick["dan"].games_diff == -9

        # Ranking by (matches_won desc, games_diff desc):
        # Charlie 2W +5, Alice 2W +3, Bob 2W +1, Dan 0W -9
        # All three of Alice/Bob/Charlie have 2 wins but different games_diff
        # so they do NOT share a rank — this is the v3-OTPP=false distinguishing
        # behavior.
        assert by_nick["charlie"].rank == 1
        assert by_nick["alice"].rank == 2
        assert by_nick["bob"].rank == 3
        assert by_nick["dan"].rank == 4
