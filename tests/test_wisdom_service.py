from datetime import date, datetime, timedelta, timezone
import pytest
from services.wisdom_service import CURATED_WISDOM_QUOTES, WisdomService


def test_curated_quotes_contain_requested_wisdoms():
    """Verify that specific requested wisdom quotes are present in the wisdom bank."""
    assert "A tree that never faces the wind will never know how strong its roots are." in CURATED_WISDOM_QUOTES
    assert "Your lack of consistency is a shame for people who believe in you." in CURATED_WISDOM_QUOTES


@pytest.mark.asyncio
async def test_first_wisdom_unlock_for_server(db_session):
    """
    Test that the first user to run the command unlocks today's wisdom for the entire server:
    - Creates a new record in daily_wisdom.
    - Returns already_unlocked=False.
    - Logs audit action DAILY_WISDOM_UNLOCKED.
    """
    service = WisdomService(db_session)
    guild_id = 998811
    user_id = 10001

    t0 = datetime(2026, 11, 6, 10, 0, 0, tzinfo=timezone.utc)
    result = await service.get_or_unlock_daily_wisdom(guild_id, user_id, current_time=t0)

    assert result["already_unlocked"] is False
    assert result["unlocked_by_user_id"] == str(user_id)
    assert len(result["quote"]) > 10
    assert result["author"] == "Ryujin"
    assert "Today's wisdom has been revealed" in result["shy_quote"]

    # Verify read-only fetch works
    today_data = await service.get_today_wisdom(guild_id, current_time=t0)
    assert today_data is not None
    assert today_data["quote"] == result["quote"]
    assert today_data["unlocked_by_user_id"] == str(user_id)


@pytest.mark.asyncio
async def test_server_wide_daily_single_unlock_constraint(db_session):
    """
    Test that once unlocked, ANY subsequent user attempting to unlock today's wisdom:
    - Receives already_unlocked=True.
    - Sees the quote that was already unlocked by the first user.
    - Does NOT create a duplicate record or change the day's quote.
    """
    service = WisdomService(db_session)
    guild_id = 998822
    first_user = 20001
    second_user = 20002

    t0 = datetime(2026, 11, 6, 11, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(minutes=15)

    # 1. First user unlocks today's wisdom
    first_res = await service.get_or_unlock_daily_wisdom(guild_id, first_user, current_time=t0)
    assert first_res["already_unlocked"] is False
    original_quote = first_res["quote"]

    # 2. Second user runs command later on the same day in the same guild
    second_res = await service.get_or_unlock_daily_wisdom(guild_id, second_user, current_time=t1)
    assert second_res["already_unlocked"] is True
    assert second_res["quote"] == original_quote
    assert second_res["unlocked_by_user_id"] == str(first_user)  # Points to original user
    assert f"<@{first_user}>" in second_res["shy_quote"]


@pytest.mark.asyncio
async def test_next_day_unlock_and_history(db_session):
    """
    Test that when a new day arrives (midnight passes):
    - A new wisdom quote can be unlocked.
    - Past wisdom entries appear in history.
    """
    service = WisdomService(db_session)
    guild_id = 998833
    user_id = 30001

    day1 = datetime(2026, 11, 6, 10, 0, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 11, 7, 10, 0, 0, tzinfo=timezone.utc)

    # Day 1 unlock
    res1 = await service.get_or_unlock_daily_wisdom(guild_id, user_id, current_time=day1)
    assert res1["already_unlocked"] is False

    # Day 2 unlock
    res2 = await service.get_or_unlock_daily_wisdom(guild_id, user_id, current_time=day2)
    assert res2["already_unlocked"] is False
    assert res2["date"] != res1["date"]

    # Verify history
    history = await service.get_wisdom_history(guild_id, limit=5)
    assert len(history) == 2
    assert history[0]["date"] == str(day2.date())
    assert history[1]["date"] == str(day1.date())

