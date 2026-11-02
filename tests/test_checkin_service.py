from datetime import datetime, timedelta, timezone
import pytest
from services.checkin_service import CheckInService


@pytest.mark.asyncio
async def test_first_time_checkin(db_session):
    """Test first-time check-in establishes streak of 1."""
    service = CheckInService(db_session)
    guild_id = 999001
    user_id = 888001

    res = await service.process_checkin(guild_id=guild_id, user_id=user_id)
    assert res["success"] is True
    assert res["already_checked_in"] is False
    assert res["streak_count"] == 1
    assert res["longest_streak"] == 1

    streak_data = await service.get_user_streak(guild_id, user_id)
    assert streak_data["current_streak"] == 1
    assert streak_data["longest_streak"] == 1


@pytest.mark.asyncio
async def test_same_day_duplicate_checkin_is_idempotent(db_session):
    """Test duplicate check-in on the same day returns existing record without double-counting."""
    service = CheckInService(db_session)
    guild_id = 999002
    user_id = 888002

    res1 = await service.process_checkin(guild_id=guild_id, user_id=user_id)
    assert res1["success"] is True
    assert res1["already_checked_in"] is False
    assert res1["streak_count"] == 1

    # Second check-in within same day
    res2 = await service.process_checkin(guild_id=guild_id, user_id=user_id)
    assert res2["success"] is True
    assert res2["already_checked_in"] is True
    assert res2["streak_count"] == 1  # Not incremented


@pytest.mark.asyncio
async def test_consecutive_day_checkin_increments_streak(db_session):
    """Test check-in on consecutive days increments the streak."""
    service = CheckInService(db_session)
    guild_id = 999003
    user_id = 888003

    day1 = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)

    res1 = await service.process_checkin(guild_id=guild_id, user_id=user_id, current_time=day1)
    assert res1["streak_count"] == 1

    res2 = await service.process_checkin(guild_id=guild_id, user_id=user_id, current_time=day2)
    assert res2["streak_count"] == 2
    assert res2["longest_streak"] == 2


@pytest.mark.asyncio
async def test_missed_day_resets_streak(db_session):
    """Test missing a day resets streak count to 1 while preserving longest_streak."""
    service = CheckInService(db_session)
    guild_id = 999004
    user_id = 888004

    day1 = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
    day4_missed = datetime(2026, 11, 4, 10, 0, tzinfo=timezone.utc)  # skipped Nov 3

    await service.process_checkin(guild_id=guild_id, user_id=user_id, current_time=day1)
    await service.process_checkin(guild_id=guild_id, user_id=user_id, current_time=day2)

    # Missed Nov 3, check in on Nov 4
    res4 = await service.process_checkin(guild_id=guild_id, user_id=user_id, current_time=day4_missed)
    assert res4["streak_count"] == 1
    assert res4["longest_streak"] == 2


@pytest.mark.asyncio
async def test_streak_leaderboard(db_session):
    """Test leaderboard returns ranked members by current streak."""
    service = CheckInService(db_session)
    guild_id = 999005

    day1 = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)

    # User A: 2 days streak
    await service.process_checkin(guild_id=guild_id, user_id=101, current_time=day1)
    await service.process_checkin(guild_id=guild_id, user_id=101, current_time=day2)

    # User B: 1 day streak
    await service.process_checkin(guild_id=guild_id, user_id=102, current_time=day2)

    leaderboard = await service.get_streak_leaderboard(guild_id=guild_id)
    assert len(leaderboard) >= 2
    assert leaderboard[0]["user_id"] == "101"
    assert leaderboard[0]["current_streak"] == 2
    assert leaderboard[1]["user_id"] == "102"
    assert leaderboard[1]["current_streak"] == 1

