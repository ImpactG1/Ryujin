from datetime import datetime, timedelta, timezone
import pytest
from services.level_service import (
    LevelPermissionError,
    LevelService,
    calculate_level_from_xp,
    xp_for_next_level,
)


def test_level_mathematics():
    """Verify XP formula and level determination logic."""
    # Level 0 requires 100 XP
    assert xp_for_next_level(0) == 100
    # Level 1 requires 155 XP
    assert xp_for_next_level(1) == 155

    # 0 XP -> level 0, 0/100
    lvl, curr, req = calculate_level_from_xp(0)
    assert lvl == 0 and curr == 0 and req == 100

    # 60 XP -> level 0, 60/100
    lvl, curr, req = calculate_level_from_xp(60)
    assert lvl == 0 and curr == 60 and req == 100

    # 100 XP -> level 1, 0/155
    lvl, curr, req = calculate_level_from_xp(100)
    assert lvl == 1 and curr == 0 and req == 155

    # 150 XP -> level 1, 50/155
    lvl, curr, req = calculate_level_from_xp(150)
    assert lvl == 1 and curr == 50 and req == 155


@pytest.mark.asyncio
async def test_message_activity_and_cooldown(db_session):
    """
    Test message count increment and anti-spam XP cooldown:
    - Message count increments on every message.
    - XP is only awarded once every 60 seconds.
    """
    service = LevelService(db_session)
    guild_id = 999111
    user_id = 777111

    t0 = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    t1 = t0 + timedelta(seconds=20)  # within 60s cooldown
    t2 = t0 + timedelta(seconds=65)  # after 60s cooldown

    # 1. First message -> awards XP (20 XP)
    res0 = await service.process_message_activity(guild_id, user_id, current_time=t0, base_xp=20)
    assert res0["messages_count"] == 1
    assert res0["total_xp"] == 20
    assert res0["xp_gained"] == 20
    assert res0["level"] == 0
    assert res0["leveled_up"] is False

    # 2. Rapid second message -> increments message count, but NO new XP granted due to cooldown
    res1 = await service.process_message_activity(guild_id, user_id, current_time=t1, base_xp=20)
    assert res1["messages_count"] == 2
    assert res1["total_xp"] == 20  # Still 20
    assert res1["xp_gained"] == 0

    # 3. Third message after 65s -> cooldown reset, awards another 20 XP
    res2 = await service.process_message_activity(guild_id, user_id, current_time=t2, base_xp=20)
    assert res2["messages_count"] == 3
    assert res2["total_xp"] == 40
    assert res2["xp_gained"] == 20


@pytest.mark.asyncio
async def test_level_up_event_trigger(db_session):
    """Test that crossing the XP threshold triggers leveled_up=True and updates level."""
    service = LevelService(db_session)
    guild_id = 999222
    user_id = 777222

    # Grant user enough XP to reach Level 1 (threshold is 100 XP)
    now = datetime(2026, 11, 1, 10, 0, 0, tzinfo=timezone.utc)
    res = await service.process_message_activity(guild_id, user_id, current_time=now, base_xp=110)

    assert res["total_xp"] == 110
    assert res["level"] == 1
    assert res["leveled_up"] is True
    assert res["old_level"] == 0
    assert res["current_level_xp"] == 10
    assert res["xp_needed_for_next"] == 155


@pytest.mark.asyncio
async def test_rank_card_and_leaderboard(db_session):
    """Test rank position calculation and community leaderboard ranking."""
    service = LevelService(db_session)
    guild_id = 999333

    now = datetime.now(timezone.utc)
    # User A: 200 XP
    await service.process_message_activity(guild_id, 1001, current_time=now, base_xp=200)
    # User B: 50 XP
    await service.process_message_activity(guild_id, 1002, current_time=now, base_xp=50)

    card_a = await service.get_member_rank_card(guild_id, 1001)
    card_b = await service.get_member_rank_card(guild_id, 1002)

    assert card_a["rank"] == 1
    assert card_a["total_xp"] == 200
    assert card_b["rank"] == 2
    assert card_b["total_xp"] == 50

    leaderboard = await service.get_xp_leaderboard(guild_id, limit=5)
    assert len(leaderboard) == 2
    assert leaderboard[0]["discord_user_id"] == "1001"
    assert leaderboard[1]["discord_user_id"] == "1002"


@pytest.mark.asyncio
async def test_admin_adjust_xp(db_session):
    """Test officer manual adjustment of XP and role permission checks."""
    service = LevelService(db_session)
    guild_id = 999444
    officer_id = 888001
    member_id = 888002

    # Non-officer cannot adjust
    with pytest.raises(LevelPermissionError):
        await service.admin_adjust_xp(
            guild_id=guild_id,
            officer_id=member_id,
            officer_roles=["member"],
            target_user_id=member_id,
            xp_delta=100,
        )

    # Officer adjusts XP
    updated_card = await service.admin_adjust_xp(
        guild_id=guild_id,
        officer_id=officer_id,
        officer_roles=["officer"],
        target_user_id=member_id,
        xp_delta=250,
    )
    assert updated_card["total_xp"] == 250
    assert updated_card["level"] == 1
