import pytest
from httpx import ASGITransport, AsyncClient

from api.dependencies import get_db_session
from api.main import app
from core.security import create_access_token


@pytest.mark.asyncio
async def test_tournament_api_full_flow(db_session):
    """
    Test tournament REST API endpoints:
    - Create tournament (officer only)
    - Register participants
    - Generate bracket (officer only)
    - Fetch bracket
    - Report score
    - Standings calculation
    """
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db

    guild_id = 999777
    officer_id = 111777
    p1_id = 222777
    p2_id = 333777

    officer_token = create_access_token({"sub": str(officer_id), "guild_id": str(guild_id), "roles": ["officer"]})
    p1_token = create_access_token({"sub": str(p1_id), "guild_id": str(guild_id), "roles": ["member"]})
    p2_token = create_access_token({"sub": str(p2_id), "guild_id": str(guild_id), "roles": ["member"]})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create tournament
        tourney_payload = {
            "title": "API Championship",
            "max_participants": 2,
        }
        res_create = await client.post(
            f"/api/v1/guilds/{guild_id}/tournaments",
            json=tourney_payload,
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert res_create.status_code == 201
        tourney_id = res_create.json()["id"]

        # 2. Register p1 & p2
        res_reg1 = await client.post(
            f"/api/v1/guilds/{guild_id}/tournaments/{tourney_id}/register",
            headers={"Authorization": f"Bearer {p1_token}"},
        )
        assert res_reg1.status_code == 200

        res_reg2 = await client.post(
            f"/api/v1/guilds/{guild_id}/tournaments/{tourney_id}/register",
            headers={"Authorization": f"Bearer {p2_token}"},
        )
        assert res_reg2.status_code == 200

        # 3. Generate bracket
        res_bracket = await client.post(
            f"/api/v1/guilds/{guild_id}/tournaments/{tourney_id}/generate-bracket",
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert res_bracket.status_code == 200
        matches = res_bracket.json()
        assert len(matches) == 1
        match_id = matches[0]["id"]

        # 4. Fetch bracket
        res_get_bracket = await client.get(f"/api/v1/guilds/{guild_id}/tournaments/{tourney_id}/bracket")
        assert res_get_bracket.status_code == 200
        assert len(res_get_bracket.json()) == 1

        # 5. Report score (p1 wins 2 - 0)
        res_score = await client.post(
            f"/api/v1/guilds/{guild_id}/tournaments/{tourney_id}/matches/{match_id}/score",
            json={"score1": 2, "score2": 0},
            headers={"Authorization": f"Bearer {p1_token}"},
        )
        assert res_score.status_code == 200
        assert res_score.json()["winner_id"] == str(p1_id)

        # 6. Fetch standings
        res_standings = await client.get(f"/api/v1/guilds/{guild_id}/tournaments/{tourney_id}/standings")
        assert res_standings.status_code == 200
        standings = res_standings.json()
        assert len(standings) == 2
        assert standings[0]["discord_user_id"] == str(p1_id)
        assert standings[0]["status"] == "Champion"
        assert standings[1]["discord_user_id"] == str(p2_id)
        assert standings[1]["status"] == "Runner-Up"

    app.dependency_overrides.clear()

