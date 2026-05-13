from __future__ import annotations

from app.domain.aggregates.league.entities import AllowlistEntry
from app.domain.aggregates.league.value_objects import (
    AllowlistEntryId,
    LeagueId,
    PlayerNickname,
)
from app.infrastructure.persistence.models.orm_models import AllowlistEntryORM


def allowlist_entry_to_domain(orm: AllowlistEntryORM) -> AllowlistEntry:
    return AllowlistEntry(
        allowlist_entry_id=AllowlistEntryId(value=orm.allowlist_entry_id),
        nickname=PlayerNickname(orm.nickname_normalized),
    )


def allowlist_entry_to_orm(
    domain: AllowlistEntry, league_id: LeagueId
) -> AllowlistEntryORM:
    return AllowlistEntryORM(
        allowlist_entry_id=domain.allowlist_entry_id.value,
        league_id=league_id.value,
        nickname_normalized=domain.nickname.value,
    )
