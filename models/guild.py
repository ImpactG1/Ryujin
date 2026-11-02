from sqlalchemy import BigInteger, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from core.database import Base
from models.base import TimestampMixin


class Guild(Base, TimestampMixin):
    __tablename__ = "guilds"

    guild_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Kolkata", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    config: Mapped["GuildConfig"] = relationship("GuildConfig", back_populates="guild", uselist=False, cascade="all, delete-orphan")


class GuildConfig(Base, TimestampMixin):
    __tablename__ = "guild_configs"

    guild_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("guilds.guild_id", ondelete="CASCADE"), primary_key=True)
    chat_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    announcement_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    recruitment_channel_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    admin_role_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    officer_role_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    captain_role_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    guild: Mapped["Guild"] = relationship("Guild", back_populates="config")

