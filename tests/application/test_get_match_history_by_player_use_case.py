"""Unit tests for GetMatchHistoryByPlayerUseCase."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.get_match_history_use_case import MatchHistoryRecord
from app.application.use_cases.get_match_history_by_player_use_case import (
    GetMatchHistoryByPlayerQuery,
    GetMatchHistoryByPlayerUseCase,
)
from app.domain.exceptions import LeagueNotFoundError, PlayerNotFoundError
from tests.application.conftest import make_league, make_match


class TestGetMatchHistoryByPlayerUseCase:
    def _use_case(
        self, league_repo: AsyncMock, match_repo: AsyncMock
    ) -> GetMatchHistoryByPlayerUseCase:
        return GetMatchHistoryByPlayerUseCase(league_repo, match_repo)

    async def test_league_not_found_raises(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        mock_league_repo.get_by_id.return_value = None
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(LeagueNotFoundError):
            await use_case.execute(
                GetMatchHistoryByPlayerQuery(
                    league_id="00000000-0000-0000-0000-000000000000",
                    player_name="alice",
                )
            )

    async def test_player_not_found_raises(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_pair("alice", "bob")
        mock_league_repo.get_by_id.return_value = league
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(PlayerNotFoundError):
            await use_case.execute(
                GetMatchHistoryByPlayerQuery(
                    league_id=str(league.league_id),
                    player_name="unknown_player",
                )
            )

    async def test_player_name_lookup_is_case_insensitive(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_pair("alice", "bob")
        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_player.return_value = []
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(
            GetMatchHistoryByPlayerQuery(league_id=str(league.league_id), player_name="ALICE")
        )
        assert result == []

    async def test_player_name_lookup_accepts_alias(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        alice = league.add_players(["alice"])[0]
        league.add_alias_to_player(str(alice.player_id.value), "ali")
        league.register_players_and_pair("alice", "bob")
        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_player.return_value = []
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(
            GetMatchHistoryByPlayerQuery(
                league_id=str(league.league_id),
                player_name="ALI",
            )
        )

        assert result == []
        mock_match_repo.get_all_by_player.assert_awaited_once()

    async def test_returns_empty_list_when_player_has_no_pair(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        _, pair = league.register_players_and_pair("alice", "bob")
        league.delete_pair(str(pair.pair_id.value))

        mock_league_repo.get_by_id.return_value = league
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(
            GetMatchHistoryByPlayerQuery(league_id=str(league.league_id), player_name="alice")
        )
        assert result == []
        mock_match_repo.get_all_by_player.assert_not_called()

    async def test_returns_empty_list_when_player_has_no_matches(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_pair("alice", "bob")
        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_player.return_value = []
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(
            GetMatchHistoryByPlayerQuery(league_id=str(league.league_id), player_name="alice")
        )
        assert result == []

    async def test_returns_only_matches_involving_players_pair(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_pair("alice", "bob")
        league.register_players_and_pair("charlie", "diana")
        league.register_players_and_pair("edgar", "frank")
        pair_alice = league.pairs[0]
        pair_charlie = league.pairs[1]
        pair_edgar = league.pairs[2]

        match_with_alice = make_match(league.league_id, pair_alice.pair_id, pair_charlie.pair_id, "6", "3")
        match_without_alice = make_match(league.league_id, pair_charlie.pair_id, pair_edgar.pair_id, "4", "6")

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_player.return_value = [match_with_alice]
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(
            GetMatchHistoryByPlayerQuery(league_id=str(league.league_id), player_name="alice")
        )

        assert len(result) == 1
        assert result[0].match_id == str(match_with_alice.match_id)

    async def test_returned_records_contain_correct_nicknames(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_pair("alice", "bob")
        league.register_players_and_pair("charlie", "diana")
        pair1 = league.pairs[0]
        pair2 = league.pairs[1]
        match = make_match(league.league_id, pair1.pair_id, pair2.pair_id, "6", "3")

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_player.return_value = [match]
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(
            GetMatchHistoryByPlayerQuery(league_id=str(league.league_id), player_name="alice")
        )

        assert len(result) == 1
        record = result[0]
        assert isinstance(record, MatchHistoryRecord)
        pair1_nicks = {record.pair1_player1_nickname, record.pair1_player2_nickname}
        pair2_nicks = {record.pair2_player1_nickname, record.pair2_player2_nickname}
        assert pair1_nicks == {
            p.nickname.value
            for p in league.players
            if p.player_id in (pair1.player_id_1, pair1.player_id_2)
        }
        assert pair2_nicks == {
            p.nickname.value
            for p in league.players
            if p.player_id in (pair2.player_id_1, pair2.player_id_2)
        }

    async def test_results_sorted_newest_first(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_pair("alice", "bob")
        league.register_players_and_pair("charlie", "diana")
        pair1 = league.pairs[0]
        pair2 = league.pairs[1]

        older_match = make_match(league.league_id, pair1.pair_id, pair2.pair_id)
        older_match.created_at = datetime(2025, 1, 1)

        newer_match = make_match(league.league_id, pair2.pair_id, pair1.pair_id)
        newer_match.created_at = datetime(2025, 6, 1)

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_player.return_value = [newer_match, older_match]
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(
            GetMatchHistoryByPlayerQuery(league_id=str(league.league_id), player_name="alice")
        )

        assert result[0].match_id == str(newer_match.match_id)
        assert result[1].match_id == str(older_match.match_id)

    async def test_also_returns_matches_where_player_pair_is_pair2(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_pair("alice", "bob")
        league.register_players_and_pair("charlie", "diana")
        pair_alice = league.pairs[0]
        pair_charlie = league.pairs[1]

        match = make_match(league.league_id, pair_charlie.pair_id, pair_alice.pair_id, "3", "6")

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_player.return_value = [match]
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(
            GetMatchHistoryByPlayerQuery(league_id=str(league.league_id), player_name="alice")
        )

        assert len(result) == 1
        assert result[0].match_id == str(match.match_id)

    async def test_otpp_false_unions_matches_across_player_pairs(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        """v3: under OTPP=false, the player may be on multiple pairs.

        The use case collects every pair the player belongs to and asks the
        repo for the union of matches across those pairs.
        """
        from app.domain.aggregates.league.aggregate_root import League
        from app.domain.aggregates.league.league_rules import LeagueRules

        rules = LeagueRules.from_dict(
            {
                "version": 3,
                "pair_matchup_idempotency": "once_per_league",
                "one_pair_per_player": False,
                "ranking_subject": "pair",
                "tie_breakers": ["matches_won"],
            }
        )
        league = League.create(
            "OTPP-False League", None, "host", host_email="host@example.com", rules=rules
        )
        league.register_players_and_pair("alice", "bob")
        league.register_players_and_pair("alice", "charlie")
        pair_ab = league.pairs[0]
        pair_ac = league.pairs[1]
        league.register_players_and_pair("diana", "edgar")
        pair_de = league.pairs[2]

        match_ab_de = make_match(league.league_id, pair_ab.pair_id, pair_de.pair_id, "6", "4")
        match_ac_de = make_match(league.league_id, pair_ac.pair_id, pair_de.pair_id, "3", "6")

        mock_league_repo.get_by_id.return_value = league
        # Repo returns matches from both of Alice's pairs.
        mock_match_repo.get_all_by_player.return_value = [match_ab_de, match_ac_de]

        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(
            GetMatchHistoryByPlayerQuery(league_id=str(league.league_id), player_name="alice")
        )

        assert len(result) == 2
        ids = {r.match_id for r in result}
        assert ids == {str(match_ab_de.match_id), str(match_ac_de.match_id)}

        # Verify the use case passed both of Alice's pair IDs to the repo.
        mock_match_repo.get_all_by_player.assert_awaited_once()
        call_args = mock_match_repo.get_all_by_player.await_args
        assert call_args.args[0] == league.league_id
        passed_pair_ids = set(call_args.args[1])
        assert passed_pair_ids == {pair_ab.pair_id, pair_ac.pair_id}
