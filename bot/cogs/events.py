from datetime import datetime, timezone
import discord
from discord import app_commands
from discord.ext import commands

from core.database import async_session_factory
from core.permissions import require_discord_role
from services.event_service import EventAttendanceWindowError, EventService


class EventsCog(commands.Cog, name="Events"):
    """Discord slash commands for community events, attendance, and reminders."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    event_group = app_commands.Group(name="event", description="Community event management")

    @event_group.command(name="create", description="Schedule a new community event (Officer+ only)")
    @require_discord_role("officer")
    async def create_event_cmd(
        self,
        interaction: discord.Interaction,
        title: str,
        start_time_iso: str,
        end_time_iso: str,
        description: str | None = None,
    ):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        try:
            start_dt = datetime.fromisoformat(start_time_iso)
            end_dt = datetime.fromisoformat(end_time_iso)
        except ValueError:
            await interaction.response.send_message("Invalid timestamp format. Please use ISO 8601 (e.g. 2026-11-05T18:00:00Z).", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)
        guild_id = interaction.guild.id
        user_id = interaction.user.id
        roles = [r.name.lower() for r in getattr(interaction.user, "roles", [])]

        async with async_session_factory() as session:
            service = EventService(session)
            event = await service.create_event(
                guild_id=guild_id,
                creator_id=user_id,
                creator_roles=roles,
                title=title,
                start_time=start_dt,
                end_time=end_dt,
                description=description,
            )
            await session.commit()

        embed = discord.Embed(
            title=f"Event Scheduled: {event.title}",
            color=discord.Color.green(),
            description=event.description or "No description provided.",
        )
        embed.add_field(name="Event ID", value=str(event.id), inline=True)
        embed.add_field(name="Start Time", value=str(event.start_time), inline=True)
        embed.add_field(name="End Time", value=str(event.end_time), inline=True)
        embed.set_footer(text="Automated reminders have been scheduled (24h, 1h, 15m before start).")

        await interaction.followup.send(embed=embed)

    @event_group.command(name="list", description="List upcoming scheduled community events")
    async def list_events_cmd(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        async with async_session_factory() as session:
            service = EventService(session)
            events = await service.list_events(guild_id=guild_id, status="scheduled")

        embed = discord.Embed(
            title="Upcoming Community Events",
            color=discord.Color.blue(),
        )
        if not events:
            embed.description = "No upcoming events found."
        else:
            for ev in events[:10]:
                embed.add_field(
                    name=f"#{ev.id} - {ev.title}",
                    value=f"Starts: {ev.start_time.isoformat()}\nStatus: {ev.status}",
                    inline=False,
                )

        await interaction.response.send_message(embed=embed)

    @event_group.command(name="cancel", description="Cancel an event (Officer+ only)")
    @require_discord_role("officer")
    async def cancel_event_cmd(self, interaction: discord.Interaction, event_id: int):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        roles = [r.name.lower() for r in getattr(interaction.user, "roles", [])]
        async with async_session_factory() as session:
            service = EventService(session)
            await service.cancel_event(
                event_id=event_id,
                canceller_id=interaction.user.id,
                canceller_roles=roles,
            )
            await session.commit()

        await interaction.response.send_message(f"Event #{event_id} has been cancelled and its reminders purged.")

    @app_commands.command(name="attend", description="Mark your attendance for an active event during its check-in window")
    async def attend_cmd(self, interaction: discord.Interaction, event_id: int):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        user_id = interaction.user.id
        async with async_session_factory() as session:
            service = EventService(session)
            try:
                res = await service.record_attendance(event_id=event_id, user_id=user_id)
                await session.commit()
                await interaction.response.send_message(f"{res['message']} (Status: {res['status']})")
            except EventAttendanceWindowError as e:
                await interaction.response.send_message(f"Attendance Failed: {str(e)}", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EventsCog(bot))
