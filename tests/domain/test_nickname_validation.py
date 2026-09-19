import pytest

from app.domain.aggregates.league.aggregate_root import League
from app.domain.aggregates.league.entities import Player
from app.domain.aggregates.league.value_objects import PlayerId, PlayerNickname
from app.domain.exceptions import InvalidPlayerNicknameError
from app.domain.nicknames import NICKNAME_WHITESPACE


@pytest.mark.parametrize("name", ["Alice", "민수", "A-1", "B_2", "C.3", "\u0085Alice"])
def test_valid_names(name):
    assert PlayerNickname(name).value == name.lower()


@pytest.mark.parametrize("space", NICKNAME_WHITESPACE)
def test_exact_whitespace_set(space):
    assert PlayerNickname(space + "Alice" + space).value == "alice"
    with pytest.raises(InvalidPlayerNicknameError):
        PlayerNickname("Alice" + space + "Bob")
    with pytest.raises(InvalidPlayerNicknameError):
        PlayerNickname(space)


@pytest.mark.parametrize("name", ["", " ", "Alice Smith", "Alice,Bob", "Alice\tBob", "Alice\nBob", "Alice\u00a0Bob"])
@pytest.mark.parametrize("operation", ["add", "rename", "alias", "singles", "doubles"])
def test_aggregate_write_paths_reject_invalid_names(name, operation):
    league = League.create("Nicknames", None, "token", "host@example.com")
    player = league.add_players(["existing"])[0]
    operations = {
        "add": lambda: league.add_players(["valid", name]),
        "rename": lambda: league.edit_player_nickname(str(player.player_id), name),
        "alias": lambda: league.add_alias_to_player(str(player.player_id), name),
        "singles": lambda: league.register_single_player(name),
        "doubles": lambda: league.register_players_and_pair("valid", name),
    }
    with pytest.raises(InvalidPlayerNicknameError):
        operations[operation]()
    assert len(league.players) == 1
    assert not league.pairs


def test_legacy_names_can_be_read_corrected_and_removed():
    league = League.create("Legacy", None, "token", "host@example.com")
    player = Player(PlayerId.generate(), nicknames=[
        PlayerNickname.from_persisted("alice smith"),
        PlayerNickname.from_persisted("alice,bob"),
    ])
    league.players.append(player)
    assert player.has_nickname(PlayerNickname.for_lookup(" Alice Smith "))
    league.remove_alias_from_player(str(player.player_id), "ALICE,BOB")
    league.edit_player_nickname(str(player.player_id), "  Alice  ")
    assert player.nickname.value == "alice"
    league.remove_player(str(player.player_id))
    assert not league.players


@pytest.mark.parametrize("name", ["\ufeffold\ufeff", "\u0085new\u0085", "old name", "old,name"])
def test_removing_alias_preserves_both_legacy_and_current_whitespace_semantics(name):
    league = League.create("Legacy", None, "token", "host@example.com")
    player = league.add_players(["canonical"])[0]
    player.nicknames.append(PlayerNickname.from_persisted(name))
    league.remove_alias_from_player(str(player.player_id), name)
    assert player.aliases == []
