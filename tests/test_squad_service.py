from datetime import datetime, timezone
import pytest
from services.event_service import EventService
from services.squad_service import (
    AlreadyMemberError,
    InvalidRequestStateError,
    PendingRequestExistsError,
    SquadFullError,
    SquadPermissionError,
    SquadService,
)


@pytest.mark.asyncio
async def test_squad_creation_and_captain_assignment(db_session):
    """Test squad creation sets captain as first member and enforces capacity."""
    service = SquadService(db_session)
    guild_id = 555001
    officer_id = 666001
    captain_id = 777001

    squad = await service.create_squad(
        guild_id=guild_id,
        creator_id=officer_id,
        creator_roles=["officer"],
        name="Phoenix Squad",
        captain_id=captain_id,
        capacity=3,
    )

    assert squad.id is not None
    assert squad.name == "Phoenix Squad"
    assert squad.capacity == 3

    # Verify captain is already in squad roster
    members = await service.list_members(squad.id)
    assert len(members) == 1
    assert members[0].discord_user_id == captain_id
    assert members[0].role == "captain"


@pytest.mark.asyncio
async def test_squad_join_request_state_machine(db_session):
    """
    Test join request lifecycle:
    Pending -> Approved / Rejected, permission enforcement (captain or officer only),
    and invalid state transitions.
    """
    service = SquadService(db_session)
    guild_id = 555002
    officer_id = 666002
    captain_id = 777002
    member_id = 888002
    outsider_id = 999002

    squad = await service.create_squad(
        guild_id=guild_id,
        creator_id=officer_id,
        creator_roles=["officer"],
        name="Titan Squad",
        captain_id=captain_id,
        capacity=2,  # Captain + 1 spot
    )

    # 1. Member requests to join -> status is pending
    req = await service.request_to_join(squad.id, member_id)
    assert req.id is not None
    assert req.status == "pending"

    # 2. Duplicate join request while pending -> raises PendingRequestExistsError
    with pytest.raises(PendingRequestExistsError):
        await service.request_to_join(squad.id, member_id)

    # 3. Unauthorized review attempt (regular member) -> raises SquadPermissionError
    with pytest.raises(SquadPermissionError):
        await service.review_join_request(
            request_id=req.id,
            reviewer_id=outsider_id,
            reviewer_roles=["member"],
            decision="approved",
        )

    # 4. Captain reviews and approves -> status approved & user added to roster
    reviewed_req = await service.review_join_request(
        request_id=req.id,
        reviewer_id=captain_id,
        reviewer_roles=["member"],  # Even if role is just member, captain_id matches!
        decision="approved",
        notes="Welcome to the squad!",
    )
    assert reviewed_req.status == "approved"

    # Member is now in roster
    roster = await service.list_members(squad.id)
    assert len(roster) == 2
    roster_ids = {m.discord_user_id for m in roster}
    assert member_id in roster_ids

    # 5. Invalid state: cannot review an already resolved request
    with pytest.raises(InvalidRequestStateError):
        await service.review_join_request(
            request_id=req.id,
            reviewer_id=officer_id,
            reviewer_roles=["officer"],
            decision="rejected",
        )

    # 6. Capacity cap: squad is now full (capacity=2). Another user attempts to join
    user3_id = 111003
    with pytest.raises(SquadFullError):
        await service.request_to_join(squad.id, user3_id)


@pytest.mark.asyncio
async def test_aggregated_squad_attendance_stats(db_session):
    """Test aggregated squad attendance calculation across events and roster members."""
    squad_service = SquadService(db_session)
    event_service = EventService(db_session)

    guild_id = 555003
    officer_id = 666003
    captain_id = 777003
    member_id = 888003

    squad = await squad_service.create_squad(
        guild_id=guild_id,
        creator_id=officer_id,
        creator_roles=["officer"],
        name="Vanguard Squad",
        captain_id=captain_id,
        capacity=5,
    )
    # Add member
    await squad_service.squad_repo.add_member(squad.id, member_id, role="member")

    # Create 2 events
    now = datetime.now(timezone.utc)
    ev1 = await event_service.create_event(
        guild_id=guild_id,
        creator_id=officer_id,
        creator_roles=["officer"],
        title="Event 1",
        start_time=now,
        end_time=now,
        target_squad_id=squad.id,
    )
    ev2 = await event_service.create_event(
        guild_id=guild_id,
        creator_id=officer_id,
        creator_roles=["officer"],
        title="Event 2",
        start_time=now,
        end_time=now,
        target_squad_id=squad.id,
    )

    # Captain attends both events; Member attends ev1 only
    await event_service.record_attendance(ev1.id, captain_id, current_time=now)
    await event_service.record_attendance(ev2.id, captain_id, current_time=now)
    await event_service.record_attendance(ev1.id, member_id, current_time=now)

    stats = await squad_service.get_squad_attendance_stats(squad.id)
    assert stats["squad_id"] == squad.id
    assert stats["member_count"] == 2
    assert stats["total_events"] == 2
    assert stats["total_attendances"] == 3
    # 3 attendances out of 4 possible (2 members * 2 events) = 75.0%
    assert stats["attendance_rate_percent"] == 75.0

