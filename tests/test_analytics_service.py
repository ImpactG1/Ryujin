from datetime import date, datetime, timedelta, timezone
import pytest
from httpx import ASGITransport, AsyncClient

from api.dependencies import get_db_session
from api.main import app
from services.analytics_service import AnalyticsService
from services.checkin_service import CheckInService
from services.event_service import EventService
from services.moderation_service import ModerationService
from services.recruitment_service import RecruitmentService


@pytest.mark.asyncio
async def test_analytics_overview_service(db_session):
    """
    Test aggregated overview metrics:
    - Member counts
    - Active streaks
    - Upcoming events
    - Open recruitment and leave requests
    - Moderation sanction statistics
    """
    analytics = AnalyticsService(db_session)
    checkin_svc = CheckInService(db_session)
    event_svc = EventService(db_session)
    mod_svc = ModerationService(db_session)
    rec_svc = RecruitmentService(db_session)

    guild_id = 999111
    user1 = 10001
    officer = 20002

    # 1. Add members and checkin
    await checkin_svc.process_checkin(guild_id, user1)

    # 2. Add upcoming event
    now = datetime.now(timezone.utc)
    await event_svc.create_event(
        guild_id=guild_id,
        creator_id=officer,
        creator_roles=["officer"],
        title="Weekly Tournament",
        start_time=now + timedelta(days=1),
        end_time=now + timedelta(days=1, hours=2),
    )

    # 3. Add open recruitment application
    await rec_svc.submit_public_application(
        guild_id=guild_id,
        discord_tag="Rookie#0001",
        email="rookie@gmail.com",
        full_name="Rookie Player",
        experience="Beginner",
    )

    # 4. Apply a moderation sanction
    await mod_svc.apply_sanction(
        guild_id=guild_id,
        moderator_id=officer,
        moderator_roles=["officer"],
        target_user_id=user1,
        sanction_type="warn",
        reason="Language warning",
    )

    # 5. Fetch overview
    overview = await analytics.get_overview(guild_id)
    assert overview["guild_id"] == guild_id
    assert overview["attendance"]["active_streaks"] >= 1
    assert overview["events"]["upcoming_count"] >= 1
    assert len(overview["events"]["next_events"]) >= 1
    assert overview["open_requests"]["recruitment_applications"] >= 1
    assert overview["moderation"]["active_sanctions_count"] >= 1
    assert overview["moderation"]["breakdown"]["warn"] >= 1


@pytest.mark.asyncio
async def test_analytics_api_endpoints_and_pagination(db_session):
    """Test dashboard overview and paginated members list endpoints."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db

    guild_id = 999222
    analytics = AnalyticsService(db_session)

    # Pre-populate members
    for i in range(15):
        await analytics.guild_repo.session.flush()
        from models.member import Member
        db_session.add(Member(
            guild_id=guild_id,
            discord_user_id=50000 + i,
            username=f"player_{i}",
            display_name=f"Player {i}",
            is_active=(i % 2 == 0),
        ))
    await db_session.flush()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Overview API
        res_overview = await client.get(f"/api/v1/guilds/{guild_id}/analytics/overview")
        assert res_overview.status_code == 200
        data = res_overview.json()
        assert data["members"]["total"] == 15
        assert data["members"]["active"] == 8

        # 2. Paginated members API (Page 1, size 5)
        res_page1 = await client.get(f"/api/v1/guilds/{guild_id}/members?page=1&page_size=5")
        assert res_page1.status_code == 200
        p1_data = res_page1.json()
        assert len(p1_data["items"]) == 5
        assert p1_data["total"] == 15
        assert p1_data["total_pages"] == 3

        # 3. Filter active only
        res_active = await client.get(f"/api/v1/guilds/{guild_id}/members?active_only=true")
        assert res_active.status_code == 200
        assert res_active.json()["total"] == 8

    app.dependency_overrides.clear()

