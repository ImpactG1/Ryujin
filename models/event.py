from datetime import datetime
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.database import Base
from models.base import TimestampMixin, utc_now


class Event(Base, TimestampMixin):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.guild_id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    creator_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    target_squad_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("squads.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="scheduled", nullable=False)  # scheduled, cancelled, completed

    reminders: Mapped[list["EventReminder"]] = relationship("EventReminder", back_populates="event", cascade="all, delete-orphan")
    attendees: Mapped[list["EventAttendance"]] = relationship("EventAttendance", back_populates="event", cascade="all, delete-orphan")


class EventReminder(Base, TimestampMixin):
    __tablename__ = "event_reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    scheduled_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reminder_type: Mapped[str] = mapped_column(String(20), nullable=False)  # '24h', '1h', '15m'
    dispatched: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    event: Mapped["Event"] = relationship("Event", back_populates="reminders")

    __table_args__ = (
        UniqueConstraint("event_id", "reminder_type", name="uq_event_reminder_type"),
    )


class EventAttendance(Base, TimestampMixin):
    __tablename__ = "event_attendance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="present", nullable=False)  # present, excused, absent
    marked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    event: Mapped["Event"] = relationship("Event", back_populates="attendees")

    __table_args__ = (
        UniqueConstraint("event_id", "discord_user_id", name="uq_event_attendee"),
    )

