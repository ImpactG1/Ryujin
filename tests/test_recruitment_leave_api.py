from datetime import date
import pytest
from httpx import ASGITransport, AsyncClient

from api.dependencies import get_db_session
from api.main import app
from core.security import create_access_token


@pytest.mark.asyncio
async def test_recruitment_and_leave_api_endpoints(db_session):
    """
    Test recruitment & leave REST API endpoints:
    - Public application submission (no auth)
    - Officer application review (auto-provision)
    - Leave request with conflict detection
    - Leave request overlapping conflict (409 Conflict)
    """
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db

    guild_id = 999555
    officer_id = 111555
    member_id = 222555

    officer_token = create_access_token({"sub": str(officer_id), "guild_id": str(guild_id), "roles": ["officer"]})
    member_token = create_access_token({"sub": str(member_id), "guild_id": str(guild_id), "roles": ["member"]})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Public application submission (NO AUTH HEADER)
        app_payload = {
            "discord_tag": "Spectre#0001",
            "email": "spectre@gaming.com",
            "full_name": "Spectre Agent",
            "experience": "Semi-pro tournament experience",
            "discord_user_id": 9990001,
        }
        res_apply = await client.post(
            f"/api/v1/guilds/{guild_id}/recruitment/apply",
            json=app_payload,
        )
        assert res_apply.status_code == 201
        app_data = res_apply.json()
        app_id = app_data["id"]
        # Assert PII is masked
        assert "spectre@gaming.com" not in app_data["email"]

        # 2. Officer reviews and approves application
        res_review = await client.post(
            f"/api/v1/guilds/{guild_id}/recruitment/applications/{app_id}/review",
            json={"decision": "approved"},
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert res_review.status_code == 200
        assert res_review.json()["status"] == "approved"
        assert res_review.json()["auto_provisioned_member_id"] == "9990001"

        # 3. Member submits leave request
        leave_payload = {
            "start_date": "2026-12-01",
            "end_date": "2026-12-05",
            "reason": "College semester exams",
        }
        res_leave = await client.post(
            f"/api/v1/guilds/{guild_id}/leave-requests",
            json=leave_payload,
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert res_leave.status_code == 201
        leave_id = res_leave.json()["id"]

        # 4. Member submits overlapping leave request -> 409 Conflict
        res_overlap = await client.post(
            f"/api/v1/guilds/{guild_id}/leave-requests",
            json={
                "start_date": "2026-12-03",
                "end_date": "2026-12-07",
                "reason": "Overlapping request",
            },
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert res_overlap.status_code == 409

        # 5. Officer approves leave request
        res_leave_rev = await client.post(
            f"/api/v1/guilds/{guild_id}/leave-requests/{leave_id}/review",
            json={"decision": "approved"},
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert res_leave_rev.status_code == 200
        assert res_leave_rev.json()["status"] == "approved"

    app.dependency_overrides.clear()

