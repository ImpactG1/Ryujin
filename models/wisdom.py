from datetime import date, datetime
from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from core.database import Base
from models.base import utc_now


class DailyWisdom(Base):
    """
    Daily wisdom quote for a guild.
    Can be unlocked by any member, but only ONCE per day for the entire server.
    """
    __tablename__ = "daily_wisdom"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.guild_id", ondelete="CASCADE"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(String(100), default="Ryujin", nullable=False)
    unlocked_by_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unlocked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("guild_id", "date", name="uq_guild_daily_wisdom"),
    )

