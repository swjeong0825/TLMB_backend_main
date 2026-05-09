"""Unit tests for GetStandingsByPlayerUseCase."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.get_standings_by_player_use_case import (
    GetStandingsByPlayerQuery,
    GetStandingsByPlayerUseCase,
)
from app.domain.aggregates.league.aggregate_root import League
from app.domain.aggregates.league.league_rules import LeagueRules
from app.domain.exceptions import LeagueNotFoundError, PlayerNotFoundError
from app.domain.services.standings_calculator import StandingsEntry
from tests.application.conftest import make_league, make_match


class TestGetStandingsByPlayerUseCase:
    def _use_case(
        self, league_repo: AsyncMock, match_repo: AsyncMock
    ) -> GetStandingsByPlayerUseCase:
        return GetStandingsByPlayerUseCase(league_repo, match_repo)

    async def test_league_not_found_raises(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        mock_league_repo.get_by_id.return_value = None
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(LeagueNotFoundError):
            await use_case.execute(
                GetStandingsByPlayerQuery(
                    league_id="00000000-0000-0000-0000-000000000000",
                    player_name="alice",
                )
            )

    async def test_player_not_found_raises(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_team("alice", "bob")
        mock_league_repo.get_by_id.return_value = league
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(PlayerNotFoundError):
            await use_case.execute(
                GetStandingsByPlayerQuery(
                    league_id=str(league.league_id),
                    player_name="unknown_player",
                )
            )

    async def test_player_name_lookup_is_case_insensitive(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_team("alice", "bob")
        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_league.return_value = []
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(
            GetStandingsByPlayerQuery(league_id=str(league.league_id), player_name="ALICE")
        )
        assert len(result.entries) == 1
        assert isinstance(result.entries[0], StandingsEntry)
        assert result.tie_breakers == league.rules.tie_breakers

    async def test_returns_empty_when_player_has_no_team(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        _, team = league.register_players_and_team("alice", "bob")
        league.delete_team(str(team.team_id.value))

        mock_league_repo.get_by_id.return_value = league
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(
            GetStandingsByPlayerQuery(league_id=str(league.league_id), player_name="alice")
        )
        assert result.entries == []
        assert result.tie_breakers == league.rules.tie_breakers

    async def test_returns_single_entry_with_league_rank(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_team("alice", "bob")
        league.register_players_and_team("charlie", "diana")
        team1 = league.teams[0]
        team2 = league.teams[1]
        match = make_match(league.league_id, team1.team_id, team2.team_id, "6", "3")

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_league.return_value = [match]
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(
            GetStandingsByPlayerQuery(league_id=str(league.league_id), player_name="charlie")
        )

        assert len(result.entries) == 1
        assert result.entries[0].team_id == str(team2.team_id.value)
        assert result.entries[0].wins == 0
        assert result.entries[0].losses == 1
        assert result.entries[0].rank == 2

    async def test_match_repo_queried_with_league_id(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_team("alice", "bob")
        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_league.return_value = []
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        await use_case.execute(
            GetStandingsByPlayerQuery(league_id=str(league.league_id), player_name="alice")
        )

        mock_match_repo.get_all_by_league.assert_awaited_once_with(league.league_id)

    async def test_player_subject_returns_players_own_row(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        """Player-subject + OTPP=false (the only player-subject combo legal in v3)."""
        rules = LeagueRules.from_dict(
            {
                "version": 3,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": False,
                "ranking_subject": "player",
                "tie_breakers": ["matches_won"],
            }
        )
        league = League.create(
            title="Player-Ranked League",
            description=None,
            host_token="host",
            rules=rules,
        )
        league.register_players_and_team("alice", "bob")
        league.register_players_and_team("charlie", "diana")
        team1 = league.teams[0]
        team2 = league.teams[1]
        match = make_match(league.league_id, team1.team_id, team2.team_id, "6", "3")

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_league.return_value = [match]
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(
            GetStandingsByPlayerQuery(league_id=str(league.league_id), player_name="charlie")
        )

        assert len(result.entries) == 1
        assert result.entries[0].subject_kind == "player"
        assert result.entries[0].nickname == "charlie"
        assert result.entries[0].team_id is None
        assert result.entries[0].wins == 0
        assert result.entries[0].losses == 1
        assert result.tie_breakers == ("matches_won",)

    async def test_team_subject_otpp_false_returns_all_player_team_rows(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        """v3: under (team, OTPP=false), a player on multiple teams gets multiple rows."""
        rules = LeagueRules.from_dict(
            {
                "version": 3,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": False,
                "ranking_subject": "team",
                "tie_breakers": ["matches_won"],
            }
        )
        league = League.create(
            title="OTPP-False Team-Ranked",
            description=None,
            host_token="host",
            rules=rules,
        )
        # Alice is on two teams (Alice+Bob and Alice+Charlie).
        league.register_players_and_team("alice", "bob")
        league.register_players_and_team("alice", "charlie")
        league.register_players_and_team("diana", "edgar")
        team_ab = league.teams[0]
        team_ac = league.teams[1]
        team_de = league.teams[2]

        # One match per Alice team so each row has distinct stats.
        match_ab_de = make_match(league.league_id, team_ab.team_id, team_de.team_id, "6", "4")
        match_ac_de = make_match(league.league_id, team_ac.team_id, team_de.team_id, "3", "6")

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_league.return_value = [match_ab_de, match_ac_de]
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(
            GetStandingsByPlayerQuery(league_id=str(league.league_id), player_name="alice")
        )

        assert len(result.entries) == 2
        team_ids = {e.team_id for e in result.entries}
        assert team_ids == {str(team_ab.team_id.value), str(team_ac.team_id.value)}
        for e in result.entries:
            assert e.subject_kind == "team"

    async def test_player_subject_otpp_false_returns_one_player_row(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        """v3: under (player, OTPP=false), the array is a single player row even if the player is on multiple teams."""
        rules = LeagueRules.from_dict(
            {
                "version": 3,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": False,
                "ranking_subject": "player",
                "tie_breakers": ["matches_won"],
            }
        )
        league = League.create(
            title="OTPP-False Player-Ranked",
            description=None,
            host_token="host",
            rules=rules,
        )
        league.register_players_and_team("alice", "bob")
        league.register_players_and_team("alice", "charlie")
        league.register_players_and_team("diana", "edgar")
        team_ab = league.teams[0]
        team_de = league.teams[2]

        match = make_match(league.league_id, team_ab.team_id, team_de.team_id, "6", "4")

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_league.return_value = [match]
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(
            GetStandingsByPlayerQuery(league_id=str(league.league_id), player_name="alice")
        )

        assert len(result.entries) == 1
        assert result.entries[0].subject_kind == "player"
        assert result.entries[0].nickname == "alice"
