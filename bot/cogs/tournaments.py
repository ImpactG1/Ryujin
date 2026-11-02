import discord
from discord import app_commands
from discord.ext import commands

from core.database import async_session_factory
from core.permissions import require_discord_role
from services.tournament_service import TournamentService


class TournamentsCog(commands.Cog, name="Tournaments"):
    """Discord slash commands for community tournaments, brackets, scores, and disputes."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    tourney_group = app_commands.Group(name="tournament", description="Community tournament management")

    @tourney_group.command(name="register", description="Register for an open community tournament")
    async def register_cmd(self, interaction: discord.Interaction, tournament_id: int):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        async with async_session_factory() as session:
            service = TournamentService(session)
            try:
                part = await service.register_participant(tournament_id, interaction.user.id)
                await session.commit()
                await interaction.response.send_message(
                    f"Registered successfully for Tournament #{tournament_id}! Your seed is **#{part.seed}**."
                )
            except Exception as e:
                await interaction.response.send_message(f"Registration Failed: {str(e)}", ephemeral=True)

    @tourney_group.command(name="bracket", description="View the current tournament bracket and match status")
    async def bracket_cmd(self, interaction: discord.Interaction, tournament_id: int):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        async with async_session_factory() as session:
            service = TournamentService(session)
            matches = await service.list_matches(tournament_id)

        embed = discord.Embed(
            title=f"Tournament #{tournament_id} Bracket",
            color=discord.Color.purple(),
        )

        if not matches:
            embed.description = "No bracket generated yet."
        else:
            for m in matches:
                p1_text = f"<@{m.participant1_id}>" if m.participant1_id else "TBD"
                p2_text = f"<@{m.participant2_id}>" if m.participant2_id else ("BYE" if m.round_number == 1 else "TBD")
                score_text = f"({m.score1} - {m.score2})" if m.status == "completed" else ""
                winner_text = f" -> Winner: <@{m.winner_id}>" if m.winner_id else ""
                embed.add_field(
                    name=f"R{m.round_number} Match {m.match_number} [{m.status.upper()}]",
                    value=f"{p1_text} vs {p2_text} {score_text}{winner_text}",
                    inline=False,
                )

        await interaction.response.send_message(embed=embed)

    @tourney_group.command(name="dispute", description="Raise an official dispute on a match result")
    async def dispute_cmd(self, interaction: discord.Interaction, match_id: int, reason: str):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        async with async_session_factory() as session:
            service = TournamentService(session)
            try:
                disp = await service.raise_dispute(match_id, interaction.user.id, reason)
                await session.commit()
                await interaction.response.send_message(
                    f"Dispute #{disp.id} raised on Match #{match_id}. Officers have been alerted for review."
                )
            except Exception as e:
                await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TournamentsCog(bot))
