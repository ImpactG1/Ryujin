from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from core.logger import logger
from core.permissions import has_sufficient_role
from core.scheduler import scheduler
from models.event import Event
from repositories.audit_repo import AuditRepository
from repositories.event_repo import EventRepository
from repositories.guild_repo import GuildRepository


class EventPermissionError(Exception):
    pass


class EventAttendanceWindowError(Exception):
    pass


class EventNotFoundError(Exception):
    pass


class EventService:
    REMINDER_OFFSETS = {
        "24h": timedelta(hours=24),
        "1h": timedelta(hours=1),
        "15m": timedelta(minutes=15),
    }

    def __init__(self, session: AsyncSession):
        self.session = session
        self.event_repo = EventRepository(session)
        self.guild_repo = GuildRepository(session)
        self.audit_repo = AuditRepository(session)

    async def _schedule_event_reminders(self, event: Event) -> None:
        """Schedule automated reminder jobs and save reminder records in DB."""
        now = datetime.now(timezone.utc)
        # Ensure event start_time is tz-aware UTC
        start_time = event.start_time
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)

        for rem_type, offset in self.REMINDER_OFFSETS.items():
            rem_time = start_time - offset
            if rem_time > now:
                # Store in DB
                reminder_obj = await self.event_repo.create_reminder(
                    event_id=event.id,
                    scheduled_time=rem_time,
                    reminder_type=rem_type,
                )
                # Register in APScheduler if running
                job_id = f"event_{event.id}_{rem_type}"
                try:
                    if scheduler.running:
                        scheduler.add_job(
                            self.dispatch_reminder,
                            "date",
                            run_date=rem_time,
                            args=[reminder_obj.id, event.id, rem_type],
                            id=job_id,
                            replace_existing=True,
                        )
                except Exception as e:
                    logger.warning("Could not add scheduler job %s: %s", job_id, e)

    def _purge_scheduler_jobs(self, event_id: int) -> None:
        for rem_type in self.REMINDER_OFFSETS.keys():
            job_id = f"event_{event_id}_{rem_type}"
            try:
                if scheduler.running and scheduler.get_job(job_id):
                    scheduler.remove_job(job_id)
            except Exception as e:
                logger.debug("Scheduler job removal for %s: %s", job_id, e)

    async def dispatch_reminder(self, reminder_id: int, event_id: int, reminder_type: str) -> bool:
        """
        Atomic dispatch handler: claims reminder in DB to guarantee it fires exactly once
        even across concurrent workers.
        """
        claimed = await self.event_repo.claim_atomic_dispatch(reminder_id)
        if not claimed:
            logger.info("Reminder %s for event %s was already dispatched. Skipping duplicate.", reminder_id, event_id)
            return False

        logger.info("Reminder %s (%s) for event %s dispatched successfully.", reminder_id, reminder_type, event_id)
        return True

    async def create_event(
        self,
        guild_id: int,
        creator_id: int,
        creator_roles: List[str] | str,
        title: str,
        start_time: datetime,
        end_time: datetime,
        description: Optional[str] = None,
        target_squad_id: Optional[int] = None,
    ) -> Event:
        # 1. Enforce officer+ permission rule
        if not has_sufficient_role(creator_roles, "officer"):
            raise EventPermissionError("Only officers or higher can create events.")

        await self.guild_repo.get_or_create_guild(guild_id)
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        if end_time.tzinfo is None:
            end_time = end_time.replace(tzinfo=timezone.utc)

        # 2. Persist event
        event = await self.event_repo.create_event(
            guild_id=guild_id,
            title=title,
            start_time=start_time,
            end_time=end_time,
            creator_id=creator_id,
            description=description,
            target_squad_id=target_squad_id,
        )

        # 3. Schedule reminders
        await self._schedule_event_reminders(event)

        # 4. Audit log
        await self.audit_repo.log_action(
            guild_id=guild_id,
            actor_id=creator_id,
            action="EVENT_CREATE",
            target_entity="event",
            target_id=str(event.id),
            details={"title": title, "start_time": str(start_time)},
        )

        return event

    async def update_event(
        self,
        event_id: int,
        editor_id: int,
        editor_roles: List[str] | str,
        title: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        description: Optional[str] = None,
        target_squad_id: Optional[int] = None,
    ) -> Event:
        if not has_sufficient_role(editor_roles, "officer"):
            raise EventPermissionError("Only officers or higher can update events.")

        event = await self.event_repo.get_event(event_id)
        if not event:
            raise EventNotFoundError(f"Event {event_id} not found.")

        time_changed = False
        updates: Dict[str, Any] = {}
        if title is not None:
            updates["title"] = title
        if description is not None:
            updates["description"] = description
        if target_squad_id is not None:
            updates["target_squad_id"] = target_squad_id
        if start_time is not None:
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
            updates["start_time"] = start_time
            time_changed = True
        if end_time is not None:
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)
            updates["end_time"] = end_time

        event = await self.event_repo.update_event(event, **updates)

        if time_changed:
            # Reschedule reminders: remove existing jobs and undispatched DB entries
            self._purge_scheduler_jobs(event.id)
            await self.event_repo.purge_undispatched_reminders(event.id)
            await self._schedule_event_reminders(event)

        await self.audit_repo.log_action(
            guild_id=event.guild_id,
            actor_id=editor_id,
            action="EVENT_UPDATE",
            target_entity="event",
            target_id=str(event.id),
            details={"time_changed": time_changed, "updated_fields": list(updates.keys())},
        )
        return event

    async def cancel_event(
        self,
        event_id: int,
        canceller_id: int,
        canceller_roles: List[str] | str,
    ) -> Event:
        if not has_sufficient_role(canceller_roles, "officer"):
            raise EventPermissionError("Only officers or higher can cancel events.")

        event = await self.event_repo.get_event(event_id)
        if not event:
            raise EventNotFoundError(f"Event {event_id} not found.")

        event.status = "cancelled"
        # Purge reminders from scheduler and DB
        self._purge_scheduler_jobs(event.id)
        await self.event_repo.purge_undispatched_reminders(event.id)
        await self.session.flush()

        await self.audit_repo.log_action(
            guild_id=event.guild_id,
            actor_id=canceller_id,
            action="EVENT_CANCEL",
            target_entity="event",
            target_id=str(event.id),
        )
        return event

    async def record_attendance(
        self,
        event_id: int,
        user_id: int,
        current_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Record member attendance with strict window enforcement:
        Window is [start_time - 15m, start_time + 30m].
        """
        event = await self.event_repo.get_event(event_id)
        if not event:
            raise EventNotFoundError(f"Event {event_id} not found.")

        if event.status == "cancelled":
            raise EventAttendanceWindowError("Cannot mark attendance for a cancelled event.")

        now = current_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        start = event.start_time
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)

        window_start = start - timedelta(minutes=15)
        window_end = start + timedelta(minutes=30)

        if now < window_start:
            raise EventAttendanceWindowError(
                f"Attendance window not open yet. It opens 15 minutes before start ({window_start.isoformat()})."
            )
        if now > window_end:
            raise EventAttendanceWindowError(
                f"Attendance window has closed. It closed 30 minutes after start ({window_end.isoformat()})."
            )

        # Check existing attendance (Idempotent)
        existing = await self.event_repo.get_attendance(event_id, user_id)
        if existing:
            return {
                "success": True,
                "already_marked": True,
                "status": existing.status,
                "marked_at": str(existing.marked_at),
                "message": "Attendance already marked.",
            }

        att = await self.event_repo.mark_attendance(event_id, user_id, status="present")
        await self.audit_repo.log_action(
            guild_id=event.guild_id,
            actor_id=user_id,
            action="EVENT_ATTENDANCE",
            target_entity="event",
            target_id=str(event.id),
            details={"status": "present"},
        )

        return {
            "success": True,
            "already_marked": False,
            "status": "present",
            "marked_at": str(att.marked_at),
            "message": "Attendance recorded successfully!",
        }

    async def get_event(self, event_id: int) -> Optional[Event]:
        return await self.event_repo.get_event(event_id)

    async def list_events(self, guild_id: int, status: Optional[str] = None, limit: int = 50) -> List[Event]:
        return await self.event_repo.list_events(guild_id=guild_id, status=status, limit=limit)

    async def list_attendees(self, event_id: int):
        return await self.event_repo.list_attendees(event_id)

