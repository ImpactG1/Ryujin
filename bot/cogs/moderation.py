import discord
from discord import app_commands
from discord.ext import commands

from core.database import async_session_factory
from core.permissions import require_discord_role
from services.moderation_service import ModerationService


class ModerationCog(commands.Cog, name="Moderation"):
    """Discord slash commands for community moderation sanctions: warn, mute, kick, ban."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="warn", description="Issue a formal warning to a community member (Officer+ only)")
    @require_discord_role("officer")
    async def warn_cmd(self, interaction: discord.Interaction, target: discord.Member, reason: str):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        roles = [r.name.lower() for r in getattr(interaction.user, "roles", [])]
        async with async_session_factory() as session:
            service = ModerationService(session)
            sanction = await service.apply_sanction(
                guild_id=interaction.guild.id,
                moderator_id=interaction.user.id,
                moderator_roles=roles,
                target_user_id=target.id,
                sanction_type="warn",
                reason=reason,
            )
            await session.commit()

        embed = discord.Embed(
            title="Member Warned",
            color=discord.Color.yellow(),
            description=f"<@{target.id}> has received a warning (Sanction #{sanction.id}).",
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.set_footer(text=f"Moderator: {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="mute", description="Temporarily mute a member (Officer+ only)")
    @require_discord_role("officer")
    async def mute_cmd(self, interaction: discord.Interaction, target: discord.Member, duration_minutes: int, reason: str):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        roles = [r.name.lower() for r in getattr(interaction.user, "roles", [])]
        async with async_session_factory() as session:
            service = ModerationService(session)
            sanction = await service.apply_sanction(
                guild_id=interaction.guild.id,
                moderator_id=interaction.user.id,
                moderator_roles=roles,
                target_user_id=target.id,
                sanction_type="mute",
                reason=reason,
                duration_minutes=duration_minutes,
            )
            await session.commit()

        embed = discord.Embed(
            title="Member Muted",
            color=discord.Color.orange(),
            description=f"<@{target.id}> has been muted for {duration_minutes} minute(s).",
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.set_footer(text="Mute expiry is scheduled automatically.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="kick", description="Kick a member from the community (Officer+ only)")
    @require_discord_role("officer")
    async def kick_cmd(self, interaction: discord.Interaction, target: discord.Member, reason: str):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        roles = [r.name.lower() for r in getattr(interaction.user, "roles", [])]
        async with async_session_factory() as session:
            service = ModerationService(session)
            sanction = await service.apply_sanction(
                guild_id=interaction.guild.id,
                moderator_id=interaction.user.id,
                moderator_roles=roles,
                target_user_id=target.id,
                sanction_type="kick",
                reason=reason,
            )
            await session.commit()

        await interaction.response.send_message(f"<@{target.id}> was kicked. Reason: {reason} (Sanction #{sanction.id})")

    @app_commands.command(name="ban", description="Ban a member from the community (Officer+ only)")
    @require_discord_role("officer")
    async def ban_cmd(self, interaction: discord.Interaction, target: discord.Member, reason: str):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        roles = [r.name.lower() for r in getattr(interaction.user, "roles", [])]
        async with async_session_factory() as session:
            service = ModerationService(session)
            sanction = await service.apply_sanction(
                guild_id=interaction.guild.id,
                moderator_id=interaction.user.id,
                moderator_roles=roles,
                target_user_id=target.id,
                sanction_type="ban",
                reason=reason,
            )
            await session.commit()

        await interaction.response.send_message(f"<@{target.id}> was banned. Reason: {reason} (Sanction #{sanction.id})")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModerationCog(bot))
