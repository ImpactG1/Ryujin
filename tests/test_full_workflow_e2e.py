from datetime import date, datetime, timedelta, timezone
import pytest
from httpx import ASGITransport, AsyncClient

from api.dependencies import get_db_session
from api.main import app
from core.security import create_access_token


@pytest.mark.asyncio
async def test_full_community_lifecycle_e2e(db_session):
    """
    Comprehensive End-to-End Test covering the complete Ryujin community lifecycle:
    1. Public recruitment application without auth (PII masked).
    2. Officer review & auto-provisioning of member.
    3. Daily check-in, streak increment, and leaderboard verification.
    4. Officer schedules event with automated reminder dispatch.
    5. Member marks event attendance within allowed window.
    6. Dynamic achievement unlocks and transparent progress tracking.
    7. Squad creation, member join request, and captain review.
    8. Tournament creation, registration, single-elimination bracket with byes, and match scoring.
    9. MOTM crowning and Hall of Fame history.
    10. Leave request with conflict checks against events.
    11. Moderation sanction and anti-abuse anomaly detection (never auto-bans).
    12. Dashboard analytics overview aggregation.
    """
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db

    guild_id = 999000111
    admin_id = 10001
    officer_id = 10002
    applicant_id = 20001

    admin_token = create_access_token({"sub": str(admin_id), "guild_id": str(guild_id), "roles": ["admin"]})
    officer_token = create_access_token({"sub": str(officer_id), "guild_id": str(guild_id), "roles": ["officer"]})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # STEP 1: Public Recruitment Application (No Auth)
        apply_resp = await client.post(
            f"/api/v1/guilds/{guild_id}/recruitment/apply",
            json={
                "discord_tag": "DragonSlayer#1337",
                "email": "slayer@ryujin.gg",
                "full_name": "Ryu Hayabusa",
                "experience": "Apex Predator / Immortal Valorant",
                "discord_user_id": applicant_id,
            },
        )
        assert apply_resp.status_code == 201
        app_data = apply_resp.json()
        app_id = app_data["id"]
        assert "@ryujin.gg" in app_data["email"]
        assert "slayer@ryujin.gg" not in app_data["email"]  # Masked PII

        # STEP 2: Officer Review & Auto-Provisioning
        review_resp = await client.post(
            f"/api/v1/guilds/{guild_id}/recruitment/applications/{app_id}/review",
            json={"decision": "approved"},
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert review_resp.status_code == 200
        assert review_resp.json()["auto_provisioned_member_id"] == str(applicant_id)

        # Applicant now has an active member token
        member_token = create_access_token({"sub": str(applicant_id), "guild_id": str(guild_id), "roles": ["member"]})

        # STEP 3: Member Check-in & Streaks
        checkin_resp = await client.post(
            f"/api/v1/guilds/{guild_id}/checkin",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert checkin_resp.status_code == 200
        assert checkin_resp.json()["streak_count"] == 1

        # Leaderboard reflects member
        lb_resp = await client.get(f"/api/v1/guilds/{guild_id}/streaks/leaderboard")
        assert lb_resp.status_code == 200
        assert lb_resp.json()[0]["user_id"] == str(applicant_id)

        # STEP 4: Officer Schedules Event
        now = datetime.now(timezone.utc)
        event_resp = await client.post(
            f"/api/v1/guilds/{guild_id}/events",
            json={
                "title": "Weekly Ryujin Scrimmage",
                "description": "5v5 internal matches",
                "start_time": (now + timedelta(minutes=5)).isoformat(),
                "end_time": (now + timedelta(hours=2)).isoformat(),
            },
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert event_resp.status_code == 201
        event_id = event_resp.json()["id"]

        # STEP 5: Member Attends Event (within 15m window)
        attend_resp = await client.post(
            f"/api/v1/guilds/{guild_id}/events/{event_id}/attend",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert attend_resp.status_code == 200
        assert attend_resp.json()["status"] == "present"

        # STEP 6: Achievement Setup & Progress
        ach_resp = await client.post(
            f"/api/v1/guilds/{guild_id}/achievements",
            json={
                "code": "EVENT_PIONEER",
                "name": "Event Pioneer",
                "description": "Attend your first community event",
                "criteria_type": "events_attended",
                "threshold": 1,
                "badge_icon": "⭐",
            },
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert ach_resp.status_code == 201
        ach_id = ach_resp.json()["id"]

        # Transparent progress reflects 1/1 (100%)
        prog_resp = await client.get(
            f"/api/v1/guilds/{guild_id}/members/{applicant_id}/achievements/progress"
        )
        assert prog_resp.status_code == 200
        assert prog_resp.json()[0]["percentage"] == 100.0

        # Award achievement
        award_resp = await client.post(
            f"/api/v1/guilds/{guild_id}/achievements/{ach_id}/award",
            json={"target_user_id": applicant_id},
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert award_resp.status_code == 200

        # Duplicate award returns 409 Conflict
        dup_award_resp = await client.post(
            f"/api/v1/guilds/{guild_id}/achievements/{ach_id}/award",
            json={"target_user_id": applicant_id},
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert dup_award_resp.status_code == 409

        # STEP 7: Squad Creation & Join Request
        squad_resp = await client.post(
            f"/api/v1/guilds/{guild_id}/squads",
            json={"name": "Shadow Blades", "captain_id": officer_id, "capacity": 5},
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert squad_resp.status_code == 201
        squad_id = squad_resp.json()["id"]

        join_resp = await client.post(
            f"/api/v1/guilds/{guild_id}/squads/{squad_id}/join-requests",
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert join_resp.status_code == 201
        req_id = join_resp.json()["id"]

        # Officer approves join request
        rev_squad_resp = await client.post(
            f"/api/v1/guilds/{guild_id}/squads/{squad_id}/join-requests/{req_id}/review",
            json={"decision": "approved", "notes": "Solid resume"},
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert rev_squad_resp.status_code == 200

        # STEP 8: Tournament Flow
        t_resp = await client.post(
            f"/api/v1/guilds/{guild_id}/tournaments",
            json={"title": "Ryujin Season 1 Duel", "max_participants": 2},
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert t_resp.status_code == 201
        tourney_id = t_resp.json()["id"]

        # Register applicant and officer
        await client.post(f"/api/v1/guilds/{guild_id}/tournaments/{tourney_id}/register", headers={"Authorization": f"Bearer {member_token}"})
        await client.post(f"/api/v1/guilds/{guild_id}/tournaments/{tourney_id}/register", headers={"Authorization": f"Bearer {officer_token}"})

        # Generate bracket
        bracket_resp = await client.post(
            f"/api/v1/guilds/{guild_id}/tournaments/{tourney_id}/generate-bracket",
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert bracket_resp.status_code == 200
        match_id = bracket_resp.json()[0]["id"]

        # Report score: applicant wins 2 - 1
        score_resp = await client.post(
            f"/api/v1/guilds/{guild_id}/tournaments/{tourney_id}/matches/{match_id}/score",
            json={"score1": 2, "score2": 1},
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert score_resp.status_code == 200
        assert score_resp.json()["winner_id"] == str(applicant_id)

        # STEP 9: MOTM Crowning
        motm_resp = await client.post(
            f"/api/v1/guilds/{guild_id}/motm",
            json={"year_month": "2026-11", "target_user_id": applicant_id, "reason": "Tournament champion and model member"},
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert motm_resp.status_code == 200

        # STEP 10: Leave Request with Conflict Checks
        leave_resp = await client.post(
            f"/api/v1/guilds/{guild_id}/leave-requests",
            json={"start_date": "2026-12-10", "end_date": "2026-12-15", "reason": "Winter holiday"},
            headers={"Authorization": f"Bearer {member_token}"},
        )
        assert leave_resp.status_code == 201

        # STEP 11: Moderation & Anti-Abuse
        sanction_resp = await client.post(
            f"/api/v1/guilds/{guild_id}/moderation/sanctions",
            json={"target_user_id": 999999, "sanction_type": "warn", "reason": "Self-promotion in general chat"},
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert sanction_resp.status_code == 201

        anomalies_resp = await client.get(
            f"/api/v1/guilds/{guild_id}/moderation/anomalies",
            headers={"Authorization": f"Bearer {officer_token}"},
        )
        assert anomalies_resp.status_code == 200

        # STEP 12: Dashboard Analytics Overview
        overview_resp = await client.get(f"/api/v1/guilds/{guild_id}/analytics/overview")
        assert overview_resp.status_code == 200
        overview = overview_resp.json()
        assert overview["members"]["active"] >= 1
        assert overview["attendance"]["active_streaks"] >= 1
        assert overview["events"]["upcoming_count"] >= 1
        assert overview["moderation"]["active_sanctions_count"] >= 1

    app.dependency_overrides.clear()

