from datetime import datetime
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from core.database import Base
from models.base import TimestampMixin, utc_now


class MemberLevel(Base, TimestampMixin):
    __tablename__ = "member_levels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.guild_id", ondelete="CASCADE"), nullable=False, index=True)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rank_tier: Mapped[str] = mapped_column(String(10), default="D", nullable=False)  # D, C, B, A, S, SS, SSS
    previous_rank_tier: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rank_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    messages_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("guild_id", "discord_user_id", name="uq_guild_member_level"),
    )


class RankHistory(Base):
    """Tracks every promotion, demotion, and rank change event for a member."""
    __tablename__ = "member_rank_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.guild_id", ondelete="CASCADE"), nullable=False, index=True)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    from_tier: Mapped[str] = mapped_column(String(10), nullable=False)
    to_tier: Mapped[str] = mapped_column(String(10), nullable=False)
    change_type: Mapped[str] = mapped_column(String(20), nullable=False)  # PROMOTION, DEMOTION, DISCORD_SYNC, INITIAL
    actor_id: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)  # 0 for system/bot, or officer user_id
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
