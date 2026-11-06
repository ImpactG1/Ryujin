import discord
from discord import app_commands
from discord.ext import commands

from core.database import async_session_factory
from services.wisdom_service import WisdomService


class WisdomCog(commands.Cog, name="Daily Wisdom"):
    """Server-wide daily wisdom quote command. Can only be unlocked once per day for the entire server."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="wisdom",
        description="Reveal today's server wisdom quote (can only be unlocked once per day for the whole server)",
    )
    async def wisdom_cmd(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        user_id = interaction.user.id

        async with async_session_factory() as session:
            service = WisdomService(session)
            result = await service.get_or_unlock_daily_wisdom(guild_id=guild_id, user_id=user_id)
            await session.commit()

        if result["already_unlocked"]:
            # Already revealed today by another member or earlier
            embed = discord.Embed(
                title="Today's Server Wisdom",
                color=discord.Color.dark_purple(),
                description=f"> *\"{result['quote']}\"*\n\n— **{result['author']}**",
            )
            embed.set_footer(
                text=f"Unlocked earlier today by <@{result['unlocked_by_user_id']}> • Resets at midnight ({result['date']})"
            )
            msg_content = f"> *\"{result['shy_quote']}\"*"
            await interaction.response.send_message(content=msg_content, embed=embed)
        else:
            # Freshly unlocked for the entire server!
            embed = discord.Embed(
                title="Ryujin's Wisdom of the Day",
                color=discord.Color.gold(),
                description=f"> *\"{result['quote']}\"*\n\n— **{result['author']}**",
            )
            embed.set_footer(
                text=f"Unlocked for the server by {interaction.user.display_name} • Date: {result['date']}"
            )
            msg_content = f"> *\"{result['shy_quote']}\"*"
            await interaction.response.send_message(content=msg_content, embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WisdomCog(bot))

