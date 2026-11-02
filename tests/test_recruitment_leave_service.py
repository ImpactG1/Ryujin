from datetime import date, datetime, timedelta, timezone
import pytest
from services.event_service import EventService
from services.leave_service import LeaveConflictError, LeavePermissionError, LeaveService
from services.recruitment_service import (
    RecruitmentPermissionError,
    RecruitmentService,
)


@pytest.mark.asyncio
async def test_public_application_masks_pii(db_session):
    """Test public application submission masks PII in public response."""
    service = RecruitmentService(db_session)
    guild_id = 444001

    res = await service.submit_public_application(
        guild_id=guild_id,
        discord_tag="Shinobi#1234",
        email="john.doe@example.com",
        full_name="John Doe",
        experience="5 years competitive esports",
        answers={"role": "Duelist"},
    )

    assert res["id"] is not None
    assert res["status"] == "pending"
    # Verify email and name are masked
    assert "@example.com" in res["email"]
    assert "john.doe" not in res["email"]  # Stripped/masked
    assert res["full_name"] != "John Doe" or "*" in res["full_name"] or "[PROTECTED" in res["full_name"]


@pytest.mark.asyncio
async def test_application_review_and_auto_provisioning(db_session):
    """Test reviewing application auto-provisions a community member record upon approval."""
    service = RecruitmentService(db_session)
    guild_id = 444002
    officer_id = 555002

    app_res = await service.submit_public_application(
        guild_id=guild_id,
        discord_tag="Valkyrie#9999",
        email="valk@gaming.net",
        full_name="Jane Doe",
        experience="Top 500 Overwatch",
        discord_user_id=123999,
    )
    app_id = app_res["id"]

    # 1. Non-officer cannot review
    with pytest.raises(RecruitmentPermissionError):
        await service.review_application(
            application_id=app_id,
            reviewer_id=888001,
            reviewer_roles=["member"],
            decision="approved",
        )

    # 2. Officer approves application
    rev_res = await service.review_application(
        application_id=app_id,
        reviewer_id=officer_id,
        reviewer_roles=["officer"],
        decision="approved",
    )
    assert rev_res["status"] == "approved"
    assert rev_res["auto_provisioned_member_id"] == "123999"

    # Verify member is auto-provisioned in member repository
    member = await service.member_repo.get_member(guild_id, 123999)
    assert member is not None
    assert member.is_active is True
    assert member.username == "Valkyrie#9999"


@pytest.mark.asyncio
async def test_leave_requests_with_conflict_checks(db_session):
    """
    Test leave request validation:
    1. Overlapping leave requests trigger LeaveConflictError.
    2. Conflicting scheduled events are identified and surfaced.
    """
    leave_service = LeaveService(db_session)
    event_service = EventService(db_session)

    guild_id = 444003
    user_id = 666003
    officer_id = 777003

    # Schedule an event during the requested leave window
    event_start = datetime(2026, 11, 20, 18, 0, tzinfo=timezone.utc)
    event_end = datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc)
    ev = await event_service.create_event(
        guild_id=guild_id,
        creator_id=officer_id,
        creator_roles=["officer"],
        title="Mandatory Roster Scrim",
        start_time=event_start,
        end_time=event_end,
    )

    # User submits leave request covering Nov 18 to Nov 22
    leave1 = await leave_service.submit_leave_request(
        guild_id=guild_id,
        user_id=user_id,
        start_date=date(2026, 11, 18),
        end_date=date(2026, 11, 22),
        reason="Family vacation",
    )

    assert leave1["id"] is not None
    assert leave1["status"] == "pending"
    # Verify conflicting event was detected
    assert len(leave1["conflicting_events"]) == 1
    assert leave1["conflicting_events"][0]["id"] == ev.id
    assert leave1["conflicting_events"][0]["title"] == "Mandatory Roster Scrim"

    # Overlapping leave check: user submits another request for Nov 21 to Nov 25
    with pytest.raises(LeaveConflictError) as exc_conflict:
        await leave_service.submit_leave_request(
            guild_id=guild_id,
            user_id=user_id,
            start_date=date(2026, 11, 21),
            end_date=date(2026, 11, 25),
            reason="Another overlapping trip",
        )
    assert "overlapping" in str(exc_conflict.value).lower()

