import pytest
from httpx import ASGITransport, AsyncClient

from api.dependencies import get_db_session
from api.main import app
from services.wisdom_service import WisdomService


@pytest.mark.asyncio
async def test_wisdom_api_endpoints(db_session):
    """
    Test daily wisdom REST API endpoints:
    - GET /guilds/{guild_id}/wisdom/today (initially unrevealed)
    - POST /guilds/{guild_id}/wisdom/unlock (unlocks for guild)
    - GET /guilds/{guild_id}/wisdom/today (now reveals quote)
    - POST /guilds/{guild_id}/wisdom/unlock (second attempt returns already_unlocked=True)
    - GET /guilds/{guild_id}/wisdom/history (retrieves historical quotes)
    """
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db

    guild_id = 998844
    user_id = 40001
    second_user = 40002

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Check today's wisdom before unlock -> unlocked: False
        res_check = await client.get(f"/api/v1/guilds/{guild_id}/wisdom/today")
        assert res_check.status_code == 200
        assert res_check.json()["unlocked"] is False

        # 2. Unlock wisdom for today
        res_unlock = await client.post(
            f"/api/v1/guilds/{guild_id}/wisdom/unlock",
            json={"user_id": user_id},
        )
        assert res_unlock.status_code == 200
        unlock_data = res_unlock.json()
        assert unlock_data["already_unlocked"] is False
        assert unlock_data["unlocked_by_user_id"] == str(user_id)
        assert len(unlock_data["quote"]) > 0

        # 3. Check today's wisdom after unlock -> unlocked: True
        res_today = await client.get(f"/api/v1/guilds/{guild_id}/wisdom/today")
        assert res_today.status_code == 200
        today_data = res_today.json()
        assert today_data["unlocked"] is True
        assert today_data["data"]["quote"] == unlock_data["quote"]

        # 4. Second user attempts to unlock today -> returns already_unlocked=True
        res_unlock_2 = await client.post(
            f"/api/v1/guilds/{guild_id}/wisdom/unlock",
            json={"user_id": second_user},
        )
        assert res_unlock_2.status_code == 200
        unlock_2_data = res_unlock_2.json()
        assert unlock_2_data["already_unlocked"] is True
        assert unlock_2_data["unlocked_by_user_id"] == str(user_id)  # Points to first user

        # 5. Get wisdom history
        res_hist = await client.get(f"/api/v1/guilds/{guild_id}/wisdom/history")
        assert res_hist.status_code == 200
        hist_items = res_hist.json()
        assert len(hist_items) == 1
        assert hist_items[0]["quote"] == unlock_data["quote"]

    app.dependency_overrides.clear()

