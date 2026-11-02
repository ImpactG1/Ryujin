from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.checkin import CheckIn, MemberStreak
from models.event import Event, EventAttendance
from models.member import Member
from models.moderation import ModerationSanction
from models.recruitment import LeaveRequest, RecruitmentApplication
from models.squad import SquadJoinRequest
from models.tournament import Tournament
from repositories.guild_repo import GuildRepository


class AnalyticsService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.guild_repo = GuildRepository(session)

    async def get_overview(self, guild_id: int) -> Dict[str, Any]:
        """
        Aggregate comprehensive community management metrics:
        - Total & active members
        - Attendance rate & active streaks
        - Upcoming events
        - Open join/recruitment/leave requests
        - Moderation sanction statistics
        - Tournament summary
        """
        now = datetime.now(timezone.utc)

        # 1. Members count
        stmt_tot_members = select(func.count(Member.id)).where(Member.guild_id == guild_id)
        res_tot_members = await self.session.execute(stmt_tot_members)
        total_members = res_tot_members.scalar_one() or 0

        stmt_active_members = select(func.count(Member.id)).where(Member.guild_id == guild_id, Member.is_active == True)
        res_active_members = await self.session.execute(stmt_active_members)
        active_members = res_active_members.scalar_one() or 0

        # 2. Checkins & Streaks
        stmt_active_streaks = select(func.count(MemberStreak.id)).where(
            MemberStreak.guild_id == guild_id,
            MemberStreak.current_streak > 0,
        )
        res_active_streaks = await self.session.execute(stmt_active_streaks)
        active_streaks_count = res_active_streaks.scalar_one() or 0

        stmt_avg_streak = select(func.avg(MemberStreak.current_streak)).where(
            MemberStreak.guild_id == guild_id,
            MemberStreak.current_streak > 0,
        )
        res_avg_streak = await self.session.execute(stmt_avg_streak)
        avg_streak_val = res_avg_streak.scalar_one() or 0.0

        # 3. Events & Attendance Rate
        stmt_events_count = select(func.count(Event.id)).where(
            Event.guild_id == guild_id,
            Event.status == "scheduled",
            Event.start_time >= now,
        )
        res_events = await self.session.execute(stmt_events_count)
        upcoming_events_count = res_events.scalar_one() or 0

        stmt_next_events = (
            select(Event)
            .where(Event.guild_id == guild_id, Event.status == "scheduled")
            .order_by(Event.start_time.asc())
            .limit(3)
        )
        res_next = await self.session.execute(stmt_next_events)
        next_events = [
            {"id": e.id, "title": e.title, "start_time": e.start_time.isoformat()}
            for e in res_next.scalars().all()
        ]

        # 4. Open Requests (Recruitment + Squad Join + Leave)
        stmt_open_apps = select(func.count(RecruitmentApplication.id)).where(
            RecruitmentApplication.guild_id == guild_id,
            RecruitmentApplication.status == "pending",
        )
        res_apps = await self.session.execute(stmt_open_apps)
        open_apps_count = res_apps.scalar_one() or 0

        stmt_open_leaves = select(func.count(LeaveRequest.id)).where(
            LeaveRequest.guild_id == guild_id,
            LeaveRequest.status == "pending",
        )
        res_leaves = await self.session.execute(stmt_open_leaves)
        open_leaves_count = res_leaves.scalar_one() or 0

        # 5. Moderation Sanctions breakdown
        stmt_sanctions = select(
            ModerationSanction.sanction_type,
            func.count(ModerationSanction.id),
        ).where(
            ModerationSanction.guild_id == guild_id,
            ModerationSanction.is_active == True,
        ).group_by(ModerationSanction.sanction_type)
        res_sanctions = await self.session.execute(stmt_sanctions)
        sanctions_breakdown = {s_type: count for s_type, count in res_sanctions.all()}

        # 6. Tournaments overview
        stmt_tourneys = select(func.count(Tournament.id)).where(
            Tournament.guild_id == guild_id,
            Tournament.status.in_(["registration", "in_progress"]),
        )
        res_tourneys = await self.session.execute(stmt_tourneys)
        active_tournaments_count = res_tourneys.scalar_one() or 0

        return {
            "guild_id": guild_id,
            "members": {
                "total": total_members,
                "active": active_members,
            },
            "attendance": {
                "active_streaks": active_streaks_count,
                "average_streak": round(float(avg_streak_val), 1),
            },
            "events": {
                "upcoming_count": upcoming_events_count,
                "next_events": next_events,
            },
            "open_requests": {
                "recruitment_applications": open_apps_count,
                "leave_requests": open_leaves_count,
                "total_open": open_apps_count + open_leaves_count,
            },
            "moderation": {
                "active_sanctions_count": sum(sanctions_breakdown.values()),
                "breakdown": sanctions_breakdown,
            },
            "tournaments": {
                "active_tournaments": active_tournaments_count,
            },
        }

    async def list_members_paginated(
        self,
        guild_id: int,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        active_only: bool = False,
    ) -> Dict[str, Any]:
        offset = (page - 1) * page_size
        query = select(Member).where(Member.guild_id == guild_id)

        if active_only:
            query = query.where(Member.is_active == True)
        if search:
            query = query.where(Member.username.ilike(f"%{search}%"))

        count_stmt = select(func.count()).select_from(query.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one() or 0

        query = query.order_by(Member.joined_at.desc()).offset(offset).limit(page_size)
        members = (await self.session.execute(query)).scalars().all()

        total_pages = max(1, (total + page_size - 1) // page_size)

        return {
            "items": [
                {
                    "id": m.id,
                    "discord_user_id": str(m.discord_user_id),
                    "username": m.username,
                    "display_name": m.display_name,
                    "is_active": m.is_active,
                    "joined_at": m.joined_at.isoformat(),
                }
                for m in members
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

