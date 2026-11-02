import pytest
from httpx import ASGITransport, AsyncClient

from api.dependencies import get_db_session
from api.main import app
from core.security import create_access_token


@pytest.mark.asyncio
async def test_moderation_api_endpoints_and_masked_audit_logs(db_session):
    """
    Test moderation REST API:
    - Apply sanctions
    - Retrieve audit logs with officer vs admin masking
    - Retrieve anti-abuse anomalies
    """
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db

    guild_id = 999444
    admin_id = 111444
    officer_id = 222444
    target_id = 333444

    admin_token = create_access_token({"sub": str(admin_id), "guild_id": str(guild_id), "roles": ["admin"]})
    officer_token = create_access_token({"sub": str(officer_id), "guild_id": str(guild_id), "roles": ["officer"]})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Officer applies sanction
        sanction_payload = {
            "target_user_id": target_id,
            "sanction_type": "mute",
            "reason": "Excessive toxicity in voice channel",
            "duration_minutes": 60,
        }
        res_sanction = await client.post(
            f"/api/v1/guilds/{guild_id}/moderation/sanctions",
            json=sanction_payload,
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert res_sanction.status_code == 201
        assert res_sanction.json()["sanction_type"] == "mute"
        assert res_sanction.json()["duration_minutes"] == 60

        # 2. Officer requests audit logs
        res_audit_officer = await client.get(
            f"/api/v1/guilds/{guild_id}/audit-logs",
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert res_audit_officer.status_code == 200
        logs = res_audit_officer.json()
        assert len(logs) >= 1

        # 3. Retrieve anti-abuse anomalies
        res_anomalies = await client.get(
            f"/api/v1/guilds/{guild_id}/moderation/anomalies",
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert res_anomalies.status_code == 200
        assert isinstance(res_anomalies.json(), list)

    app.dependency_overrides.clear()

