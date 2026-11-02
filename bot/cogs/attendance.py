import discord
from discord import app_commands
from discord.ext import commands

from core.database import async_session_factory
from services.checkin_service import CheckInService


class AttendanceCog(commands.Cog, name="Attendance"):
    """Discord slash commands for community attendance, daily check-ins, and streaks."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="checkin", description="Claim your daily community check-in and maintain your streak!")
    async def checkin(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=False)
        guild_id = interaction.guild.id
        user_id = interaction.user.id

        async with async_session_factory() as session:
            service = CheckInService(session)
            result = await service.process_checkin(guild_id=guild_id, user_id=user_id)
            await session.commit()

        embed = discord.Embed(
            title="Ryujin Daily Check-In",
            color=discord.Color.green() if not result["already_checked_in"] else discord.Color.blue(),
            description=result["message"],
        )
        embed.add_field(name="Current Streak", value=f"{result['streak_count']} days", inline=True)
        embed.add_field(name="Longest Streak", value=f"{result['longest_streak']} days", inline=True)
        embed.add_field(name="Date", value=result["checkin_date"], inline=True)
        embed.set_footer(text="Keep checking in daily to earn recognition badges!")

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="streak", description="View your current and longest check-in streak.")
    async def streak(self, interaction: discord.Interaction, member: discord.Member | None = None):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        target_member = member or interaction.user
        guild_id = interaction.guild.id

        async with async_session_factory() as session:
            service = CheckInService(session)
            data = await service.get_user_streak(guild_id=guild_id, user_id=target_member.id)

        embed = discord.Embed(
            title=f"Streak Status - {target_member.display_name}",
            color=discord.Color.gold(),
        )
        embed.add_field(name="Current Streak", value=f"{data['current_streak']} days", inline=True)
        embed.add_field(name="Longest Streak", value=f"{data['longest_streak']} days", inline=True)
        embed.add_field(name="Last Check-in", value=data["last_checkin_date"] or "Never", inline=True)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard", description="View the top check-in streaks in the community.")
    async def leaderboard(self, interaction: discord.Interaction, limit: int = 10):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        capped_limit = min(max(limit, 1), 25)
        guild_id = interaction.guild.id

        async with async_session_factory() as session:
            service = CheckInService(session)
            top_streaks = await service.get_streak_leaderboard(guild_id=guild_id, limit=capped_limit)

        embed = discord.Embed(
            title="Ryujin Community Check-In Leaderboard",
            color=discord.Color.purple(),
            description="The most consistent members in the community!",
        )

        if not top_streaks:
            embed.description = "No check-ins recorded yet. Run `/checkin` to start your streak!"
        else:
            lines = []
            for idx, item in enumerate(top_streaks, start=1):
                lines.append(
                    f"**#{idx}** <@{item['user_id']}> — **{item['current_streak']}** days (Best: {item['longest_streak']})"
                )
            embed.description = "\n".join(lines)

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AttendanceCog(bot))
