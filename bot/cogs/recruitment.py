from datetime import date
import discord
from discord import app_commands
from discord.ext import commands

from core.database import async_session_factory
from core.permissions import require_discord_role
from services.leave_service import LeaveConflictError, LeaveService


class RecruitmentCog(commands.Cog, name="Recruitment"):
    """Discord slash commands for community recruitment and member leave management."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    leave_group = app_commands.Group(name="leave", description="Member leave management")

    @app_commands.command(name="apply", description="Get the public link and instructions to apply for Ryujin community membership.")
    async def apply_cmd(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Join the Ryujin Community!",
            color=discord.Color.blue(),
            description="We welcome competitive and community-driven players to apply for membership.",
        )
        embed.add_field(
            name="Application Portal",
            value="Submit your application on our web dashboard: http://localhost:3000/apply",
            inline=False,
        )
        embed.set_footer(text="No Discord login required to submit an application. PII is strictly protected.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @leave_group.command(name="request", description="Request an official leave of absence")
    async def request_leave_cmd(
        self,
        interaction: discord.Interaction,
        start_date_str: str,
        end_date_str: str,
        reason: str,
    ):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        try:
            start_d = date.fromisoformat(start_date_str)
            end_d = date.fromisoformat(end_date_str)
        except ValueError:
            await interaction.response.send_message("Invalid date format. Use YYYY-MM-DD (e.g. 2026-11-15).", ephemeral=True)
            return

        guild_id = interaction.guild.id
        user_id = interaction.user.id

        async with async_session_factory() as session:
            service = LeaveService(session)
            try:
                res = await service.submit_leave_request(
                    guild_id=guild_id,
                    user_id=user_id,
                    start_date=start_d,
                    end_date=end_d,
                    reason=reason,
                )
                await session.commit()
            except LeaveConflictError as e:
                await interaction.response.send_message(f"Conflict Error: {str(e)}", ephemeral=True)
                return
            except Exception as e:
                await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)
                return

        embed = discord.Embed(
            title=f"Leave Request #{res['id']} Submitted",
            color=discord.Color.gold(),
            description=f"Status: **{res['status']}**\nDates: {res['start_date']} to {res['end_date']}",
        )
        embed.add_field(name="Reason", value=res["reason"], inline=False)
        if res["conflicting_events"]:
            ev_titles = [f"• {ev['title']} ({ev['start_time'][:10]})" for ev in res["conflicting_events"]]
            embed.add_field(name="Notice: Conflicting Events", value="\n".join(ev_titles), inline=False)

        await interaction.response.send_message(embed=embed)

    @leave_group.command(name="review", description="Review a leave request (Officer+ only)")
    @require_discord_role("officer")
    async def review_leave_cmd(
        self,
        interaction: discord.Interaction,
        leave_id: int,
        decision: str,  # 'approved' or 'rejected'
    ):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        roles = [r.name.lower() for r in getattr(interaction.user, "roles", [])]
        async with async_session_factory() as session:
            service = LeaveService(session)
            try:
                res = await service.review_leave_request(
                    leave_id=leave_id,
                    reviewer_id=interaction.user.id,
                    reviewer_roles=roles,
                    decision=decision,
                )
                await session.commit()
                await interaction.response.send_message(f"Leave request #{res['id']} has been **{res['status']}**.")
            except Exception as e:
                await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RecruitmentCog(bot))
