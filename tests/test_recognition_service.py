from datetime import datetime, timezone
import pytest
from services.checkin_service import CheckInService
from services.event_service import EventService
from services.recognition_service import (
    DuplicateAwardError,
    RecognitionPermissionError,
    RecognitionService,
)


@pytest.mark.asyncio
async def test_dynamic_achievement_criteria_and_transparent_progress(db_session):
    """
    Test dynamic criteria evaluation (streak, events attended) and transparent progress calculation.
    """
    rec_service = RecognitionService(db_session)
    checkin_service = CheckInService(db_session)
    event_service = EventService(db_session)

    guild_id = 777001
    user_id = 888001
    officer_id = 999001

    # 1. Create achievement rules
    ach1 = await rec_service.create_achievement(
        guild_id=guild_id,
        creator_roles=["officer"],
        code="STREAK_7",
        name="Week Warrior",
        description="Maintain a 7-day check-in streak",
        criteria_type="streak",
        threshold=7,
        badge_icon="🔥",
    )

    ach2 = await rec_service.create_achievement(
        guild_id=guild_id,
        creator_roles=["admin"],
        code="EVENTS_2",
        name="Event Regular",
        description="Attend 2 scheduled community events",
        criteria_type="events_attended",
        threshold=2,
        badge_icon="🎟️",
    )

    # User performs 3 days of check-ins
    day1 = datetime(2026, 11, 1, 10, 0, tzinfo=timezone.utc)
    day2 = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
    day3 = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)
    await checkin_service.process_checkin(guild_id, user_id, current_time=day1)
    await checkin_service.process_checkin(guild_id, user_id, current_time=day2)
    await checkin_service.process_checkin(guild_id, user_id, current_time=day3)

    # User attends 1 event within window
    now = datetime.now(timezone.utc)
    event1 = await event_service.create_event(
        guild_id=guild_id,
        creator_id=officer_id,
        creator_roles=["officer"],
        title="Event 1",
        start_time=now,
        end_time=now,
    )
    await event_service.record_attendance(event1.id, user_id, current_time=now)

    # 2. Inspect transparent progress
    progress = await rec_service.get_user_progress(guild_id, user_id)
    assert len(progress) == 2

    # Check streak progress: 3/7 = 42.9%
    p_streak = next(p for p in progress if p["code"] == "STREAK_7")
    assert p_streak["current_value"] == 3
    assert p_streak["threshold"] == 7
    assert p_streak["percentage"] == 42.9
    assert p_streak["is_unlocked"] is False

    # Check event progress: 1/2 = 50.0%
    p_event = next(p for p in progress if p["code"] == "EVENTS_2")
    assert p_event["current_value"] == 1
    assert p_event["threshold"] == 2
    assert p_event["percentage"] == 50.0
    assert p_event["is_unlocked"] is False


@pytest.mark.asyncio
async def test_duplicate_award_protection(db_session):
    """Test that awarding an achievement a second time raises DuplicateAwardError."""
    service = RecognitionService(db_session)
    guild_id = 777002
    user_id = 888002
    officer_id = 999002

    ach = await service.create_achievement(
        guild_id=guild_id,
        creator_roles=["officer"],
        code="SPECIAL_VIP",
        name="VIP",
        description="Special contributor badge",
        criteria_type="streak",
        threshold=1,
    )

    # First award succeeds
    award1 = await service.award_achievement(
        guild_id=guild_id,
        user_id=user_id,
        achievement_id=ach.id,
        awarded_by=officer_id,
    )
    assert award1.id is not None

    # Duplicate award raises DuplicateAwardError
    with pytest.raises(DuplicateAwardError) as exc_info:
        await service.award_achievement(
            guild_id=guild_id,
            user_id=user_id,
            achievement_id=ach.id,
            awarded_by=officer_id,
        )
    assert "already been awarded" in str(exc_info.value)


@pytest.mark.asyncio
async def test_motm_crowning_and_history(db_session):
    """Test crowning Member of the Month and retrieving history."""
    service = RecognitionService(db_session)
    guild_id = 777003
    user_id = 888003
    officer_id = 999003

    # Crowning with member role fails
    with pytest.raises(RecognitionPermissionError):
        await service.crown_motm(
            guild_id=guild_id,
            crowned_by_id=user_id,
            crowned_by_roles=["member"],
            year_month="2026-11",
            target_user_id=user_id,
            reason="Self-crowning attempt",
        )

    # Crowning with officer role succeeds
    motm = await service.crown_motm(
        guild_id=guild_id,
        crowned_by_id=officer_id,
        crowned_by_roles=["officer"],
        year_month="2026-11",
        target_user_id=user_id,
        reason="Outstanding community participation and helping newcomers.",
    )
    assert motm.id is not None
    assert motm.year_month == "2026-11"

    # History retrieval
    history = await service.get_motm_history(guild_id)
    assert len(history) >= 1
    assert history[0].year_month == "2026-11"
    assert history[0].discord_user_id == user_id

