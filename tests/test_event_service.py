from datetime import datetime, timedelta, timezone
import pytest
from services.event_service import (
    EventAttendanceWindowError,
    EventNotFoundError,
    EventPermissionError,
    EventService,
)


@pytest.mark.asyncio
async def test_create_event_and_schedule_reminders(db_session):
    """Test event creation schedules reminders for future intervals."""
    service = EventService(db_session)
    guild_id = 1111
    creator_id = 2222

    now = datetime.now(timezone.utc)
    start_time = now + timedelta(days=2)  # 48 hours in future
    end_time = start_time + timedelta(hours=2)

    event = await service.create_event(
        guild_id=guild_id,
        creator_id=creator_id,
        creator_roles=["officer"],
        title="Weekly Community Scrim",
        start_time=start_time,
        end_time=end_time,
        description="Friendly practice match",
    )

    assert event.id is not None
    assert event.status == "scheduled"

    reminders = await service.event_repo.get_reminders_for_event(event.id)
    # Should have scheduled 24h, 1h, and 15m reminders since start_time is 48 hours away
    assert len(reminders) == 3
    reminder_types = {r.reminder_type for r in reminders}
    assert reminder_types == {"24h", "1h", "15m"}


@pytest.mark.asyncio
async def test_event_update_reschedules_reminders(db_session):
    """Test updating event start time purges old reminders and reschedules new ones."""
    service = EventService(db_session)
    guild_id = 1111
    creator_id = 2222

    now = datetime.now(timezone.utc)
    start_time = now + timedelta(days=2)
    end_time = start_time + timedelta(hours=2)

    event = await service.create_event(
        guild_id=guild_id,
        creator_id=creator_id,
        creator_roles=["admin"],
        title="Scrim v1",
        start_time=start_time,
        end_time=end_time,
    )

    old_reminders = await service.event_repo.get_reminders_for_event(event.id)
    assert len(old_reminders) == 3

    # Reschedule event to 5 days out
    new_start = now + timedelta(days=5)
    new_end = new_start + timedelta(hours=2)

    updated_event = await service.update_event(
        event_id=event.id,
        editor_id=creator_id,
        editor_roles=["admin"],
        start_time=new_start,
        end_time=new_end,
    )

    new_reminders = await service.event_repo.get_reminders_for_event(event.id)
    assert len(new_reminders) == 3
    # Check that scheduled_time for 24h reminder is now new_start - 24h
    rem_24h = next(r for r in new_reminders if r.reminder_type == "24h")
    # Compare timestamps (handle tz-naive SQLite datetime conversion)
    expected_24h = new_start - timedelta(hours=24)
    assert abs((rem_24h.scheduled_time.replace(tzinfo=timezone.utc) - expected_24h).total_seconds()) < 5


@pytest.mark.asyncio
async def test_cancel_event_purges_reminders(db_session):
    """Test cancelling an event sets status to cancelled and purges undispatched reminders."""
    service = EventService(db_session)
    guild_id = 1111
    creator_id = 2222

    now = datetime.now(timezone.utc)
    start = now + timedelta(days=2)
    end = start + timedelta(hours=1)

    event = await service.create_event(
        guild_id=guild_id,
        creator_id=creator_id,
        creator_roles=["officer"],
        title="To be cancelled",
        start_time=start,
        end_time=end,
    )

    cancelled = await service.cancel_event(
        event_id=event.id,
        canceller_id=creator_id,
        canceller_roles=["officer"],
    )
    assert cancelled.status == "cancelled"

    reminders = await service.event_repo.get_reminders_for_event(event.id)
    assert len(reminders) == 0


@pytest.mark.asyncio
async def test_atomic_reminder_dispatch(db_session):
    """Test that a reminder is claimed atomically and cannot be dispatched twice."""
    service = EventService(db_session)
    guild_id = 1111
    creator_id = 2222

    now = datetime.now(timezone.utc)
    event = await service.create_event(
        guild_id=guild_id,
        creator_id=creator_id,
        creator_roles=["officer"],
        title="Atomic Test",
        start_time=now + timedelta(hours=2),
        end_time=now + timedelta(hours=3),
    )

    reminders = await service.event_repo.get_reminders_for_event(event.id)
    assert len(reminders) >= 1
    rem = reminders[0]

    # First worker claims
    first_claim = await service.dispatch_reminder(rem.id, event.id, rem.reminder_type)
    assert first_claim is True

    # Second concurrent worker attempts to claim same reminder
    second_claim = await service.dispatch_reminder(rem.id, event.id, rem.reminder_type)
    assert second_claim is False, "Second worker must not dispatch the same reminder twice"


@pytest.mark.asyncio
async def test_attendance_window_enforcement(db_session):
    """
    Test strict attendance window:
    Valid window is [start_time - 15m, start_time + 30m].
    """
    service = EventService(db_session)
    guild_id = 1111
    creator_id = 2222
    user_id = 7777

    base_start = datetime(2026, 11, 10, 18, 0, tzinfo=timezone.utc)
    base_end = datetime(2026, 11, 10, 20, 0, tzinfo=timezone.utc)

    event = await service.create_event(
        guild_id=guild_id,
        creator_id=creator_id,
        creator_roles=["officer"],
        title="Championship Match",
        start_time=base_start,
        end_time=base_end,
    )

    # 1. 20 minutes before start -> Too early!
    too_early = base_start - timedelta(minutes=20)
    with pytest.raises(EventAttendanceWindowError) as exc_early:
        await service.record_attendance(event.id, user_id, current_time=too_early)
    assert "not open yet" in str(exc_early.value).lower()

    # 2. 10 minutes before start -> Within window!
    valid_pre_start = base_start - timedelta(minutes=10)
    res_valid = await service.record_attendance(event.id, user_id, current_time=valid_pre_start)
    assert res_valid["success"] is True
    assert res_valid["already_marked"] is False
    assert res_valid["status"] == "present"

    # 3. Duplicate marking within window -> Idempotent!
    res_dup = await service.record_attendance(event.id, user_id, current_time=base_start)
    assert res_dup["success"] is True
    assert res_dup["already_marked"] is True

    # 4. Another user 35 minutes after start -> Window closed!
    user2_id = 8888
    too_late = base_start + timedelta(minutes=35)
    with pytest.raises(EventAttendanceWindowError) as exc_late:
        await service.record_attendance(event.id, user2_id, current_time=too_late)
    assert "closed" in str(exc_late.value).lower()

