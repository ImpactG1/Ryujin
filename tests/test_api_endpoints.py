import pytest
from httpx import ASGITransport, AsyncClient
from api.dependencies import get_db_session
from api.main import app
from core.security import create_access_token


@pytest.mark.asyncio
async def test_health_check_endpoint():
    """Verify health check endpoint returns 200 OK."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["app"] == "Ryujin"


@pytest.mark.asyncio
async def test_api_checkin_flow(db_session):
    """Test check-in API endpoint with JWT Bearer token authentication."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db

    guild_id = 123456789
    user_id = 987654321
    token = create_access_token({"sub": str(user_id), "guild_id": str(guild_id), "roles": ["member"]})
    headers = {"Authorization": f"Bearer {token}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. First check-in
        resp1 = await client.post(f"/api/v1/guilds/{guild_id}/checkin", headers=headers)
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["success"] is True
        assert data1["already_checked_in"] is False
        assert data1["streak_count"] == 1

        # 2. Duplicate check-in on the same day (Idempotent)
        resp2 = await client.post(f"/api/v1/guilds/{guild_id}/checkin", headers=headers)
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["success"] is True
        assert data2["already_checked_in"] is True
        assert data2["streak_count"] == 1

        # 3. Check member streak endpoint
        resp_streak = await client.get(f"/api/v1/guilds/{guild_id}/members/{user_id}/streak")
        assert resp_streak.status_code == 200
        streak_data = resp_streak.json()
        assert streak_data["current_streak"] == 1
        assert streak_data["longest_streak"] == 1

        # 4. Check leaderboard endpoint
        resp_lb = await client.get(f"/api/v1/guilds/{guild_id}/streaks/leaderboard")
        assert resp_lb.status_code == 200
        lb_data = resp_lb.json()
        assert len(lb_data) >= 1
        assert lb_data[0]["user_id"] == str(user_id)

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_unauthorized_checkin():
    """Verify check-in endpoint rejects requests without Bearer token."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/guilds/123/checkin")
        assert response.status_code == 401

