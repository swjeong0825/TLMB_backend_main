from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def league_local_day_utc_bounds(
    now_utc: datetime, league_timezone: str
) -> tuple[datetime, datetime]:
    tz = ZoneInfo(league_timezone)
    local_day = now_utc.astimezone(tz).date()
    start_local = datetime.combine(local_day, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)
