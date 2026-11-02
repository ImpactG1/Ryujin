import discord
from discord import app_commands
from discord.ext import commands

from core.database import async_session_factory
from core.permissions import require_discord_role
from services.recognition_service import RecognitionService


class RecognitionCog(commands.Cog, name="Recognition"):
    """Discord slash commands for community achievements, awards, and Member of the Month (MOTM)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    motm_group = app_commands.Group(name="motm", description="Member of the Month management")

    @app_commands.command(name="achievements", description="View your progress toward community achievements and badges.")
    async def achievements_cmd(self, interaction: discord.Interaction, member: discord.Member | None = None):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        target_member = member or interaction.user
        guild_id = interaction.guild.id

        async with async_session_factory() as session:
            service = RecognitionService(session)
            progress = await service.get_user_progress(guild_id=guild_id, user_id=target_member.id)

        embed = discord.Embed(
            title=f"Achievements Progress — {target_member.display_name}",
            color=discord.Color.gold(),
            description="Complete milestones to unlock badges and prestige!",
        )

        if not progress:
            embed.description = "No achievements configured yet for this community."
        else:
            for item in progress:
                status_icon = "Unlocked" if item["is_unlocked"] else f"{item['percentage']}%"
                val_text = f"Progress: {item['current_value']} / {item['threshold']} ({status_icon})"
                embed.add_field(
                    name=f"{item['badge_icon'] or ''} {item['name']} [{item['code']}]",
                    value=f"{item['description']}\n{val_text}",
                    inline=False,
                )

        await interaction.response.send_message(embed=embed)

    @motm_group.command(name="crown", description="Crown the Member of the Month (Officer+ only)")
    @require_discord_role("officer")
    async def crown_motm_cmd(
        self,
        interaction: discord.Interaction,
        target_member: discord.Member,
        year_month: str,
        reason: str,
    ):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        crowned_by_id = interaction.user.id
        roles = [r.name.lower() for r in getattr(interaction.user, "roles", [])]

        async with async_session_factory() as session:
            service = RecognitionService(session)
            record = await service.crown_motm(
                guild_id=guild_id,
                crowned_by_id=crowned_by_id,
                crowned_by_roles=roles,
                year_month=year_month,
                target_user_id=target_member.id,
                reason=reason,
            )
            await session.commit()

        embed = discord.Embed(
            title=f"Member of the Month ({record.year_month})",
            color=discord.Color.purple(),
            description=f"Congratulations to <@{target_member.id}> on being crowned Member of the Month!",
        )
        embed.add_field(name="Reason", value=record.reason, inline=False)
        embed.set_footer(text=f"Crowned by {interaction.user.display_name}")

        await interaction.response.send_message(embed=embed)

    @motm_group.command(name="history", description="View the history of past Members of the Month")
    async def motm_history_cmd(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        async with async_session_factory() as session:
            service = RecognitionService(session)
            history = await service.get_motm_history(guild_id=guild_id)

        embed = discord.Embed(
            title="Member of the Month — Hall of Fame",
            color=discord.Color.purple(),
        )

        if not history:
            embed.description = "No MOTM records found."
        else:
            for item in history:
                embed.add_field(
                    name=f"Month: {item.year_month}",
                    value=f"Member: <@{item.discord_user_id}>\nReason: {item.reason}",
                    inline=False,
                )

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RecognitionCog(bot))
