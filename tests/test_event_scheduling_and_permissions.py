from datetime import datetime, timedelta, timezone
import pytest
from httpx import ASGITransport, AsyncClient

from api.dependencies import get_db_session
from api.main import app
from core.security import create_access_token
from services.event_service import EventPermissionError, EventService


@pytest.mark.asyncio
async def test_officer_role_enforcement_in_service(db_session):
    """Test that users with insufficient role (e.g. member, guest) cannot create, update, or cancel events."""
    service = EventService(db_session)
    guild_id = 2222
    creator_id = 3333
    now = datetime.now(timezone.utc)

    # 1. Member creates event -> rejected
    with pytest.raises(EventPermissionError):
        await service.create_event(
            guild_id=guild_id,
            creator_id=creator_id,
            creator_roles=["member"],
            title="Unauthorized Event",
            start_time=now + timedelta(days=1),
            end_time=now + timedelta(days=1, hours=1),
        )

    # 2. Officer creates event -> succeeds
    event = await service.create_event(
        guild_id=guild_id,
        creator_id=creator_id,
        creator_roles=["officer"],
        title="Authorized Event",
        start_time=now + timedelta(days=1),
        end_time=now + timedelta(days=1, hours=1),
    )
    assert event.id is not None

    # 3. Guest tries to update -> rejected
    with pytest.raises(EventPermissionError):
        await service.update_event(
            event_id=event.id,
            editor_id=4444,
            editor_roles=["guest"],
            title="Hacked Title",
        )

    # 4. Captain tries to cancel (captain weight is 40 < officer 60) -> rejected
    with pytest.raises(EventPermissionError):
        await service.cancel_event(
            event_id=event.id,
            canceller_id=5555,
            canceller_roles=["captain"],
        )

    # 5. Admin cancels -> succeeds
    cancelled = await service.cancel_event(
        event_id=event.id,
        canceller_id=creator_id,
        canceller_roles=["admin"],
    )
    assert cancelled.status == "cancelled"


@pytest.mark.asyncio
async def test_event_api_permissions_and_crud(db_session):
    """Test event REST API endpoints enforce role requirements (403 for member, 201 for officer)."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db

    guild_id = 999123
    member_token = create_access_token({"sub": "1001", "guild_id": str(guild_id), "roles": ["member"]})
    officer_token = create_access_token({"sub": "1002", "guild_id": str(guild_id), "roles": ["officer"]})

    now = datetime.now(timezone.utc)
    event_payload = {
        "title": "API Scrim Event",
        "description": "Testing API endpoints",
        "start_time": (now + timedelta(hours=2)).isoformat(),
        "end_time": (now + timedelta(hours=4)).isoformat(),
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Member tries to create event -> 403 Forbidden
        res_forbidden = await client.post(
            f"/api/v1/guilds/{guild_id}/events",
            json=event_payload,
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert res_forbidden.status_code == 403

        # 2. Officer creates event -> 201 Created
        res_created = await client.post(
            f"/api/v1/guilds/{guild_id}/events",
            json=event_payload,
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert res_created.status_code == 201
        event_data = res_created.json()
        event_id = event_data["id"]
        assert event_data["title"] == "API Scrim Event"

        # 3. List events -> 200 OK
        res_list = await client.get(f"/api/v1/guilds/{guild_id}/events")
        assert res_list.status_code == 200
        events_list = res_list.json()
        assert len(events_list) >= 1

        # 4. Officer updates event -> 200 OK
        res_patch = await client.patch(
            f"/api/v1/guilds/{guild_id}/events/{event_id}",
            json={"title": "Updated API Scrim Title"},
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert res_patch.status_code == 200
        assert res_patch.json()["title"] == "Updated API Scrim Title"

        # 5. Member marks attendance before window -> 400 Bad Request
        res_attend_early = await client.post(
            f"/api/v1/guilds/{guild_id}/events/{event_id}/attend",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert res_attend_early.status_code == 400
        assert "window" in res_attend_early.json()["detail"].lower()

        # 6. Officer cancels event -> 200 OK
        res_del = await client.delete(
            f"/api/v1/guilds/{guild_id}/events/{event_id}",
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert res_del.status_code == 200
        assert res_del.json()["status"] == "cancelled"

    app.dependency_overrides.clear()

