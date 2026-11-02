import discord
from discord import app_commands
from discord.ext import commands

from core.database import async_session_factory
from core.permissions import require_discord_role
from services.squad_service import SquadService


class SquadsCog(commands.Cog, name="Squads"):
    """Discord slash commands for community squads, rosters, join requests, and squad stats."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    squad_group = app_commands.Group(name="squad", description="Community squad management")

    @squad_group.command(name="create", description="Create a new squad (Officer+ only)")
    @require_discord_role("officer")
    async def create_squad_cmd(
        self,
        interaction: discord.Interaction,
        name: str,
        captain: discord.Member,
        capacity: int = 10,
    ):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        creator_id = interaction.user.id
        roles = [r.name.lower() for r in getattr(interaction.user, "roles", [])]

        async with async_session_factory() as session:
            service = SquadService(session)
            squad = await service.create_squad(
                guild_id=guild_id,
                creator_id=creator_id,
                creator_roles=roles,
                name=name,
                captain_id=captain.id,
                capacity=capacity,
            )
            await session.commit()

        embed = discord.Embed(
            title=f"Squad Created: {squad.name}",
            color=discord.Color.green(),
        )
        embed.add_field(name="Squad ID", value=str(squad.id), inline=True)
        embed.add_field(name="Captain", value=f"<@{captain.id}>", inline=True)
        embed.add_field(name="Capacity", value=str(squad.capacity), inline=True)

        await interaction.response.send_message(embed=embed)

    @squad_group.command(name="list", description="List all squads in the community")
    async def list_squads_cmd(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        async with async_session_factory() as session:
            service = SquadService(session)
            squads = await service.list_squads(guild_id)

        embed = discord.Embed(title="Community Squads", color=discord.Color.blue())
        if not squads:
            embed.description = "No squads found."
        else:
            for sq in squads:
                embed.add_field(
                    name=f"#{sq.id} {sq.name}",
                    value=f"Captain: <@{sq.captain_id}>\nCapacity: {sq.capacity}",
                    inline=False,
                )

        await interaction.response.send_message(embed=embed)

    @squad_group.command(name="join", description="Submit a join request to a squad")
    async def join_squad_cmd(self, interaction: discord.Interaction, squad_id: int):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        async with async_session_factory() as session:
            service = SquadService(session)
            try:
                req = await service.request_to_join(squad_id, interaction.user.id)
                await session.commit()
                await interaction.response.send_message(
                    f"Join request #{req.id} submitted for Squad #{squad_id}! Awaiting captain/officer review."
                )
            except Exception as e:
                await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)

    @squad_group.command(name="stats", description="View aggregated attendance stats for a squad")
    async def squad_stats_cmd(self, interaction: discord.Interaction, squad_id: int):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        async with async_session_factory() as session:
            service = SquadService(session)
            try:
                stats = await service.get_squad_attendance_stats(squad_id)
            except Exception as e:
                await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)
                return

        embed = discord.Embed(
            title=f"Squad Attendance Stats — {stats['squad_name']}",
            color=discord.Color.gold(),
        )
        embed.add_field(name="Roster Count", value=f"{stats['member_count']} / {stats['capacity']}", inline=True)
        embed.add_field(name="Total Events", value=str(stats['total_events']), inline=True)
        embed.add_field(name="Attendance Rate", value=f"{stats['attendance_rate_percent']}%", inline=True)

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SquadsCog(bot))
