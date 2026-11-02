import pytest
from httpx import ASGITransport, AsyncClient

from api.dependencies import get_db_session
from api.main import app
from core.security import create_access_token


@pytest.mark.asyncio
async def test_squad_api_endpoints(db_session):
    """
    Test squad REST API endpoints:
    - Squad creation (officer only)
    - List squads
    - Submit join request
    - Review join request (captain or officer)
    - Get stats
    """
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db

    guild_id = 999888
    officer_id = 11111
    captain_id = 22222
    member_id = 33333

    officer_token = create_access_token({"sub": str(officer_id), "guild_id": str(guild_id), "roles": ["officer"]})
    captain_token = create_access_token({"sub": str(captain_id), "guild_id": str(guild_id), "roles": ["member"]})
    member_token = create_access_token({"sub": str(member_id), "guild_id": str(guild_id), "roles": ["member"]})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create squad via API
        squad_payload = {
            "name": "Alpha Wolves",
            "captain_id": captain_id,
            "capacity": 5,
        }
        res_create = await client.post(
            f"/api/v1/guilds/{guild_id}/squads",
            json=squad_payload,
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert res_create.status_code == 201
        squad_id = res_create.json()["id"]

        # 2. List squads
        res_list = await client.get(f"/api/v1/guilds/{guild_id}/squads")
        assert res_list.status_code == 200
        assert len(res_list.json()) >= 1

        # 3. Member submits join request
        res_join = await client.post(
            f"/api/v1/guilds/{guild_id}/squads/{squad_id}/join-requests",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert res_join.status_code == 201
        req_id = res_join.json()["id"]
        assert res_join.json()["status"] == "pending"

        # 4. Captain reviews and approves request
        review_payload = {
            "decision": "approved",
            "notes": "Approved via captain review",
        }
        res_review = await client.post(
            f"/api/v1/guilds/{guild_id}/squads/{squad_id}/join-requests/{req_id}/review",
            json=review_payload,
            headers={"Authorization": f"Bearer {captain_token}"},
        )
        assert res_review.status_code == 200
        assert res_review.json()["status"] == "approved"

        # 5. Fetch squad stats
        res_stats = await client.get(f"/api/v1/guilds/{guild_id}/squads/{squad_id}/stats")
        assert res_stats.status_code == 200
        stats_data = res_stats.json()
        assert stats_data["squad_name"] == "Alpha Wolves"
        assert stats_data["member_count"] == 2

    app.dependency_overrides.clear()

