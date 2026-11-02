from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from models.event import Event, EventAttendance, EventReminder


class EventRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_event(
        self,
        guild_id: int,
        title: str,
        start_time: datetime,
        end_time: datetime,
        creator_id: int,
        description: Optional[str] = None,
        target_squad_id: Optional[int] = None,
    ) -> Event:
        event = Event(
            guild_id=guild_id,
            title=title,
            description=description,
            start_time=start_time,
            end_time=end_time,
            creator_id=creator_id,
            target_squad_id=target_squad_id,
            status="scheduled",
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def get_event(self, event_id: int) -> Optional[Event]:
        stmt = select(Event).where(Event.id == event_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_events(
        self,
        guild_id: int,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Event]:
        stmt = select(Event).where(Event.guild_id == guild_id)
        if status:
            stmt = stmt.where(Event.status == status)
        stmt = stmt.order_by(Event.start_time.asc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_event(self, event: Event, **kwargs) -> Event:
        for key, value in kwargs.items():
            if hasattr(event, key) and value is not None:
                setattr(event, key, value)
        await self.session.flush()
        return event

    async def cancel_event(self, event_id: int) -> Optional[Event]:
        event = await self.get_event(event_id)
        if event:
            event.status = "cancelled"
            await self.session.flush()
        return event

    # --- Reminders ---
    async def create_reminder(
        self,
        event_id: int,
        scheduled_time: datetime,
        reminder_type: str,
    ) -> EventReminder:
        reminder = EventReminder(
            event_id=event_id,
            scheduled_time=scheduled_time,
            reminder_type=reminder_type,
            dispatched=False,
        )
        self.session.add(reminder)
        await self.session.flush()
        return reminder

    async def get_reminders_for_event(self, event_id: int) -> List[EventReminder]:
        stmt = select(EventReminder).where(EventReminder.event_id == event_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def purge_undispatched_reminders(self, event_id: int) -> int:
        stmt = delete(EventReminder).where(
            EventReminder.event_id == event_id,
            EventReminder.dispatched == False,
        )
        result = await self.session.execute(stmt)
        return result.rowcount

    async def claim_atomic_dispatch(self, reminder_id: int) -> bool:
        """
        Atomically claim a reminder for dispatch using optimistic locking / atomic UPDATE.
        Returns True if this worker claimed the reminder, False if already dispatched.
        """
        now = datetime.now(timezone.utc)
        stmt = (
            update(EventReminder)
            .where(
                EventReminder.id == reminder_id,
                EventReminder.dispatched == False,
            )
            .values(dispatched=True, dispatched_at=now)
            .returning(EventReminder.id)
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        return row is not None

    # --- Attendance ---
    async def get_attendance(self, event_id: int, user_id: int) -> Optional[EventAttendance]:
        stmt = select(EventAttendance).where(
            EventAttendance.event_id == event_id,
            EventAttendance.discord_user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_attendance(
        self,
        event_id: int,
        user_id: int,
        status: str = "present",
    ) -> EventAttendance:
        attendance = EventAttendance(
            event_id=event_id,
            discord_user_id=user_id,
            status=status,
        )
        self.session.add(attendance)
        await self.session.flush()
        return attendance

    async def list_attendees(self, event_id: int) -> List[EventAttendance]:
        stmt = select(EventAttendance).where(EventAttendance.event_id == event_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

