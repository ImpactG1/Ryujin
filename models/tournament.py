from datetime import datetime
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.database import Base
from models.base import TimestampMixin, utc_now


class Tournament(Base, TimestampMixin):
    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.guild_id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_participants: Mapped[int] = mapped_column(Integer, default=16, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="registration", nullable=False)  # registration, in_progress, completed, cancelled
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    participants: Mapped[list["TournamentParticipant"]] = relationship("TournamentParticipant", back_populates="tournament", cascade="all, delete-orphan")
    matches: Mapped[list["TournamentMatch"]] = relationship("TournamentMatch", back_populates="tournament", cascade="all, delete-orphan")


class TournamentParticipant(Base, TimestampMixin):
    __tablename__ = "tournament_participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tournament_id: Mapped[int] = mapped_column(Integer, ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False)
    discord_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="registered", nullable=False)  # registered, checked_in, eliminated, winner
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    tournament: Mapped["Tournament"] = relationship("Tournament", back_populates="participants")

    __table_args__ = (
        UniqueConstraint("tournament_id", "discord_user_id", name="uq_tournament_participant"),
    )


class TournamentMatch(Base, TimestampMixin):
    __tablename__ = "tournament_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tournament_id: Mapped[int] = mapped_column(Integer, ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    match_number: Mapped[int] = mapped_column(Integer, nullable=False)
    participant1_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    participant2_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    score1: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    score2: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    winner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending, completed, disputed

    tournament: Mapped["Tournament"] = relationship("Tournament", back_populates="matches")
    disputes: Mapped[list["TournamentDispute"]] = relationship("TournamentDispute", back_populates="match", cascade="all, delete-orphan")


class TournamentDispute(Base, TimestampMixin):
    __tablename__ = "tournament_disputes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(Integer, ForeignKey("tournament_matches.id", ondelete="CASCADE"), nullable=False)
    raised_by_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    officer_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)  # open, resolved
    resolved_by_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    match: Mapped["TournamentMatch"] = relationship("TournamentMatch", back_populates="disputes")

