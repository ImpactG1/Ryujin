from datetime import datetime
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.database import Base
from models.base import TimestampMixin, utc_now


class Squad(Base, TimestampMixin):
    __tablename__ = "squads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.guild_id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    captain_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    members: Mapped[list["SquadMember"]] = relationship("SquadMember", back_populates="squad", cascade="all, delete-orphan")
    join_requests: Mapped[list["SquadJoinRequest"]] = relationship("SquadJoinRequest", back_populates="squad", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("guild_id", "name", name="uq_guild_squad_name"),
    )


class SquadMember(Base, TimestampMixin):
    __tablename__ = "squad_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    squad_id: Mapped[int] = mapped_column(Integer, ForeignKey("squads.id", ondelete="CASCADE"), nullable=False)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="member", nullable=False)  # captain, member
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    squad: Mapped["Squad"] = relationship("Squad", back_populates="members")

    __table_args__ = (
        UniqueConstraint("squad_id", "discord_user_id", name="uq_squad_member"),
    )


class SquadJoinRequest(Base, TimestampMixin):
    __tablename__ = "squad_join_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    squad_id: Mapped[int] = mapped_column(Integer, ForeignKey("squads.id", ondelete="CASCADE"), nullable=False)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending, approved, rejected
    reviewer_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    squad: Mapped["Squad"] = relationship("Squad", back_populates="join_requests")

