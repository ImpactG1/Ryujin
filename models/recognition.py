from datetime import datetime
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.database import Base
from models.base import TimestampMixin, utc_now


class Achievement(Base, TimestampMixin):
    __tablename__ = "achievements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.guild_id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g., 'STREAK_7', 'EVENTS_10'
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    criteria_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'streak', 'events_attended', 'tournaments_won'
    threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    badge_icon: Mapped[str | None] = mapped_column(String(50), nullable=True)

    awards: Mapped[list["MemberAward"]] = relationship("MemberAward", back_populates="achievement", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("guild_id", "code", name="uq_guild_achievement_code"),
    )


class MemberAward(Base, TimestampMixin):
    __tablename__ = "member_awards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.guild_id", ondelete="CASCADE"), nullable=False)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    achievement_id: Mapped[int] = mapped_column(Integer, ForeignKey("achievements.id", ondelete="CASCADE"), nullable=False)
    awarded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    awarded_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    achievement: Mapped["Achievement"] = relationship("Achievement", back_populates="awards")

    __table_args__ = (
        UniqueConstraint("guild_id", "discord_user_id", "achievement_id", name="uq_member_award_unique"),
    )


class MOTMRecord(Base, TimestampMixin):
    __tablename__ = "motm_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.guild_id", ondelete="CASCADE"), nullable=False)
    year_month: Mapped[str] = mapped_column(String(7), nullable=False)  # 'YYYY-MM'
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    crowned_by: Mapped[int] = mapped_column(BigInteger, nullable=False)
    awarded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("guild_id", "year_month", name="uq_guild_motm_month"),
    )

