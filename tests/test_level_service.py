from datetime import datetime, timedelta, timezone
import pytest
from services.level_service import (
    RANK_TIERS,
    LevelPermissionError,
    LevelRankError,
    LevelService,
    calculate_level_from_xp,
    generate_shy_rank_dialogue,
    get_rank_tier_from_level,
    xp_for_next_level,
)


def test_level_mathematics_and_rank_tiers():
    """Verify XP formula and rank tier determination logic."""
    assert xp_for_next_level(0) == 100
    assert xp_for_next_level(1) == 155

    lvl, curr, req = calculate_level_from_xp(0)
    assert lvl == 0 and curr == 0 and req == 100

    # Test Rank Tier mappings (D, C, B, A, S, SS, SSS)
    assert get_rank_tier_from_level(0) == "D"
    assert get_rank_tier_from_level(4) == "D"
    assert get_rank_tier_from_level(5) == "C"
    assert get_rank_tier_from_level(14) == "C"
    assert get_rank_tier_from_level(15) == "B"
    assert get_rank_tier_from_level(29) == "B"
    assert get_rank_tier_from_level(30) == "A"
    assert get_rank_tier_from_level(49) == "A"
    assert get_rank_tier_from_level(50) == "S"
    assert get_rank_tier_from_level(74) == "S"
    assert get_rank_tier_from_level(75) == "SS"
    assert get_rank_tier_from_level(99) == "SS"
    assert get_rank_tier_from_level(100) == "SSS"


def test_shy_ryujin_rank_dialogue():
    """Verify Ryujin's shy, terse, 1-line dialogue generation."""
    # Shy dialogue for normal member
    d_quote = generate_shy_rank_dialogue("D", user_id=12345)
    assert "Rank D" in d_quote
    assert len(d_quote.splitlines()) == 1  # Exactly 1 line

    s_quote = generate_shy_rank_dialogue("S", user_id=12345)
    assert "Rank S" in s_quote
    assert "*looks away*" in s_quote
    assert len(s_quote.splitlines()) == 1

    # Promotion dialogue
    promo_quote = generate_shy_rank_dialogue("A", user_id=12345, change_type="PROMOTION", from_tier="B")
    assert "Promoted from B to Rank A" in promo_quote
    assert len(promo_quote.splitlines()) == 1

    # Demotion dialogue
    demo_quote = generate_shy_rank_dialogue("C", user_id=12345, change_type="DEMOTION", from_tier="B")
    assert "Demoted from B to Rank C" in demo_quote
    assert len(demo_quote.splitlines()) == 1


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
    t1 = t0 + timedelta(seconds=20)
    t2 = t0 + timedelta(seconds=65)

    # 1. First message -> awards XP (20 XP)
    res0 = await service.process_message_activity(guild_id, user_id, current_time=t0, base_xp=20)
    assert res0["messages_count"] == 1
    assert res0["total_xp"] == 20
    assert res0["xp_gained"] == 20
    assert res0["level"] == 0
    assert res0["rank_tier"] == "D"
    assert res0["leveled_up"] is False

    # 2. Rapid second message -> no XP due to cooldown
    res1 = await service.process_message_activity(guild_id, user_id, current_time=t1, base_xp=20)
    assert res1["messages_count"] == 2
    assert res1["total_xp"] == 20
    assert res1["xp_gained"] == 0

    # 3. Third message after 65s -> awards XP
    res2 = await service.process_message_activity(guild_id, user_id, current_time=t2, base_xp=20)
    assert res2["messages_count"] == 3
    assert res2["total_xp"] == 40
    assert res2["xp_gained"] == 20


@pytest.mark.asyncio
async def test_level_up_and_auto_rank_promotion(db_session):
    """Test crossing XP threshold triggers level up and auto-promotion to higher rank tier."""
    service = LevelService(db_session)
    guild_id = 999222
    user_id = 777222

    now = datetime(2026, 11, 1, 10, 0, 0, tzinfo=timezone.utc)
    # Give enough XP to reach Level 5 (Tier C starts at level 5)
    # L0: 100, L1: 155, L2: 220, L3: 295, L4: 380 -> Sum = 1150
    res = await service.process_message_activity(guild_id, user_id, current_time=now, base_xp=1200)

    assert res["level"] >= 5
    assert res["rank_tier"] == "C"
    assert res["rank_promoted"] is True
    assert res["leveled_up"] is True


@pytest.mark.asyncio
async def test_rank_card_and_discord_sync(db_session):
    """Test rank card output and synchronizing rank tier from Discord roles."""
    service = LevelService(db_session)
    guild_id = 999333
    user_id = 1001

    # Initialize member
    await service.process_message_activity(guild_id, user_id, base_xp=50)

    # Sync Discord role (e.g. user was assigned Rank A on Discord)
    synced = await service.sync_discord_rank(guild_id=guild_id, user_id=user_id, discord_tier="A")
    assert synced["rank_tier"] == "A"
    assert synced["previous_rank_tier"] == "D"
    assert "Rank A" in synced["shy_quote"]

    # Check rank history has recorded the promotion
    history = await service.get_rank_history(guild_id, user_id)
    assert len(history) >= 1
    assert history[0]["change_type"] == "PROMOTION"
    assert history[0]["from_tier"] == "D"
    assert history[0]["to_tier"] == "A"


@pytest.mark.asyncio
async def test_officer_promote_and_demote(db_session):
    """Test officer manual promotion, demotion, and validation."""
    service = LevelService(db_session)
    guild_id = 999444
    officer_id = 888001
    member_id = 888002

    # Initialize member (starts at Rank D)
    await service.get_member_rank_card(guild_id, member_id)

    # Non-officer cannot promote
    with pytest.raises(LevelPermissionError):
        await service.promote_member(
            guild_id=guild_id,
            officer_id=member_id,
            officer_roles=["member"],
            target_user_id=member_id,
        )

    # Officer promotes to Rank C
    promoted = await service.promote_member(
        guild_id=guild_id,
        officer_id=officer_id,
        officer_roles=["officer"],
        target_user_id=member_id,
        reason="Excellent tournament gameplay",
    )
    assert promoted["rank_tier"] == "C"
    assert promoted["previous_rank_tier"] == "D"

    # Officer promotes directly to Rank S
    promoted_s = await service.promote_member(
        guild_id=guild_id,
        officer_id=officer_id,
        officer_roles=["officer"],
        target_user_id=member_id,
        target_tier="S",
        reason="MVP performance",
    )
    assert promoted_s["rank_tier"] == "S"

    # Officer demotes to Rank A
    demoted = await service.demote_member(
        guild_id=guild_id,
        officer_id=officer_id,
        officer_roles=["officer"],
        target_user_id=member_id,
        target_tier="A",
        reason="Disciplinary demotion",
    )
    assert demoted["rank_tier"] == "A"
    assert demoted["previous_rank_tier"] == "S"

    # Verify history has 3 entries
    history = await service.get_rank_history(guild_id, member_id)
    assert len(history) == 3
    assert history[0]["change_type"] == "DEMOTION"
    assert history[1]["change_type"] == "PROMOTION"
    assert history[2]["change_type"] == "PROMOTION"
