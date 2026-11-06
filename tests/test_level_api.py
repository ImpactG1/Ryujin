import pytest
from httpx import ASGITransport, AsyncClient

from api.dependencies import get_db_session
from api.main import app
from core.security import create_access_token
from services.level_service import LevelService


@pytest.mark.asyncio
async def test_levels_api_endpoints(db_session):
    """
    Test level and XP REST API endpoints:
    - GET member rank card
    - GET level leaderboard
    - POST adjust member XP (officer only)
    """
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db

    guild_id = 999888111
    officer_id = 111999
    member_id = 222999

    officer_token = create_access_token({"sub": str(officer_id), "guild_id": str(guild_id), "roles": ["officer"]})
    member_token = create_access_token({"sub": str(member_id), "guild_id": str(guild_id), "roles": ["member"]})

    # Seed member activity
    level_svc = LevelService(db_session)
    await level_svc.process_message_activity(guild_id, member_id, base_xp=150)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Get rank card
        res_rank = await client.get(f"/api/v1/guilds/{guild_id}/members/{member_id}/rank")
        assert res_rank.status_code == 200
        rank_data = res_rank.json()
        assert rank_data["level"] == 1
        assert rank_data["total_xp"] == 150
        assert rank_data["messages_count"] == 1
        assert rank_data["rank"] == 1

        # 2. Get leaderboard
        res_lb = await client.get(f"/api/v1/guilds/{guild_id}/levels/leaderboard")
        assert res_lb.status_code == 200
        lb_data = res_lb.json()
        assert len(lb_data) >= 1
        assert lb_data[0]["discord_user_id"] == str(member_id)

        # 3. Member attempts to adjust XP -> 403 Forbidden
        res_forbidden = await client.post(
            f"/api/v1/guilds/{guild_id}/members/{member_id}/xp",
            json={"xp_delta": 500},
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert res_forbidden.status_code == 403

        # 4. Officer adjusts XP -> 200 OK
        res_adjust = await client.post(
            f"/api/v1/guilds/{guild_id}/members/{member_id}/xp",
            json={"xp_delta": 200},
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert res_adjust.status_code == 200
        assert res_adjust.json()["total_xp"] == 350

    app.dependency_overrides.clear()
