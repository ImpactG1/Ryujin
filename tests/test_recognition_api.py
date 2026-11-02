import pytest
from httpx import ASGITransport, AsyncClient

from api.dependencies import get_db_session
from api.main import app
from core.security import create_access_token


@pytest.mark.asyncio
async def test_recognition_api_endpoints_and_409_conflict(db_session):
    """
    Test achievement creation, progress, duplicate award protection returning 409 Conflict,
    and MOTM crowning via REST API.
    """
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db

    guild_id = 999333
    officer_id = 1010
    target_user_id = 2020

    officer_token = create_access_token({"sub": str(officer_id), "guild_id": str(guild_id), "roles": ["officer"]})
    member_token = create_access_token({"sub": str(target_user_id), "guild_id": str(guild_id), "roles": ["member"]})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create achievement via API
        ach_payload = {
            "code": "COMMUNITY_MVP",
            "name": "Community MVP",
            "description": "Awarded for exceptional leadership",
            "criteria_type": "streak",
            "threshold": 30,
            "badge_icon": "🏆",
        }
        res_create = await client.post(
            f"/api/v1/guilds/{guild_id}/achievements",
            json=ach_payload,
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert res_create.status_code == 201
        ach_id = res_create.json()["id"]

        # 2. Check progress endpoint
        res_prog = await client.get(
            f"/api/v1/guilds/{guild_id}/members/{target_user_id}/achievements/progress"
        )
        assert res_prog.status_code == 200
        prog_data = res_prog.json()
        assert len(prog_data) >= 1
        assert prog_data[0]["code"] == "COMMUNITY_MVP"
        assert prog_data[0]["is_unlocked"] is False

        # 3. Award achievement (First time -> 200 OK)
        award_payload = {"target_user_id": target_user_id}
        res_award1 = await client.post(
            f"/api/v1/guilds/{guild_id}/achievements/{ach_id}/award",
            json=award_payload,
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert res_award1.status_code == 200
        assert res_award1.json()["discord_user_id"] == str(target_user_id)

        # 4. Duplicate Award -> MUST return 409 Conflict
        res_award2 = await client.post(
            f"/api/v1/guilds/{guild_id}/achievements/{ach_id}/award",
            json=award_payload,
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert res_award2.status_code == 409, f"Expected 409 Conflict on duplicate award, got {res_award2.status_code}"
        assert "already been awarded" in res_award2.json()["detail"]

        # 5. Crown MOTM
        motm_payload = {
            "year_month": "2026-11",
            "target_user_id": target_user_id,
            "reason": "Outstanding contributions to community projects",
        }
        res_motm = await client.post(
            f"/api/v1/guilds/{guild_id}/motm",
            json=motm_payload,
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert res_motm.status_code == 200
        assert res_motm.json()["year_month"] == "2026-11"

        # 6. MOTM History
        res_history = await client.get(f"/api/v1/guilds/{guild_id}/motm/history")
        assert res_history.status_code == 200
        history_data = res_history.json()
        assert len(history_data) >= 1
        assert history_data[0]["year_month"] == "2026-11"

    app.dependency_overrides.clear()

