import discord
from discord import app_commands
from discord.ext import commands

from core.database import async_session_factory
from services.level_service import LevelService


def create_progress_bar(percent: float, total_blocks: int = 10) -> str:
    """Generate a clean ASCII progress bar."""
    filled = int(round(total_blocks * (percent / 100.0)))
    filled = max(0, min(total_blocks, filled))
    return "█" * filled + "░" * (total_blocks - filled)


class LevelsCog(commands.Cog, name="Levels"):
    """Discord listener and slash commands for member message activity, EXP tracking, and leveling."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore bot messages or direct messages
        if message.author.bot or not message.guild:
            return

        guild_id = message.guild.id
        user_id = message.author.id

        async with async_session_factory() as session:
            service = LevelService(session)
            result = await service.process_message_activity(guild_id=guild_id, user_id=user_id)
            await session.commit()

        # If user leveled up, send a level up congratulations embed
        if result["leveled_up"]:
            embed = discord.Embed(
                title="Level Up!",
                color=discord.Color.gold(),
                description=f"GG <@{user_id}>! You just reached **Level {result['level']}**!",
            )
            embed.add_field(name="Total Messages", value=str(result["messages_count"]), inline=True)
            embed.add_field(name="Total XP", value=f"{result['total_xp']} XP", inline=True)
            embed.set_footer(text="Keep chatting to earn more XP and climb the server rank!")
            try:
                await message.channel.send(embed=embed)
            except discord.DiscordException:
                pass

    @app_commands.command(name="rank", description="Check your or another member's level, rank, XP, and message count")
    async def rank_cmd(self, interaction: discord.Interaction, member: discord.Member | None = None):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        target = member or interaction.user
        guild_id = interaction.guild.id

        async with async_session_factory() as session:
            service = LevelService(session)
            card = await service.get_member_rank_card(guild_id=guild_id, user_id=target.id)

        bar = create_progress_bar(card["progress_percent"])

        embed = discord.Embed(
            title=f"Rank & Activity — {target.display_name}",
            color=discord.Color.purple(),
        )
        if target.avatar:
            embed.set_thumbnail(url=target.avatar.url)

        embed.add_field(name="Server Rank", value=f"#{card['rank']}", inline=True)
        embed.add_field(name="Level", value=str(card["level"]), inline=True)
        embed.add_field(name="Total Messages", value=str(card["messages_count"]), inline=True)

        progress_text = (
            f"**Progress:** `{bar}` {card['progress_percent']}%\n"
            f"**XP:** {card['current_level_xp']} / {card['xp_needed_for_next']} XP (Total: {card['total_xp']} XP)"
        )
        embed.add_field(name="Level Progress", value=progress_text, inline=False)
        embed.set_footer(text="Earn 15-25 XP per minute by being active in server channels.")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="levels", description="View the community message activity and level leaderboard")
    async def levels_cmd(self, interaction: discord.Interaction, limit: int = 10):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        capped_limit = min(max(limit, 1), 25)
        guild_id = interaction.guild.id

        async with async_session_factory() as session:
            service = LevelService(session)
            leaderboard = await service.get_xp_leaderboard(guild_id=guild_id, limit=capped_limit)

        embed = discord.Embed(
            title="Ryujin Community Levels Leaderboard",
            color=discord.Color.gold(),
            description="The most active members in the server!",
        )

        if not leaderboard:
            embed.description = "No chat activity recorded yet. Start talking in channels to earn XP!"
        else:
            lines = []
            for item in leaderboard:
                lines.append(
                    f"**#{item['rank']}** <@{item['discord_user_id']}> — **Level {item['level']}** "
                    f"({item['total_xp']} XP • {item['messages_count']} msgs)"
                )
            embed.description = "\n".join(lines)

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LevelsCog(bot))
