from datetime import datetime
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from core.database import async_session_factory
from core.permissions import has_sufficient_role
from services.level_service import (
    RANK_TIERS,
    LevelPermissionError,
    LevelRankError,
    LevelService,
)


def create_progress_bar(percent: float, total_blocks: int = 10) -> str:
    """Generate a clean ASCII progress bar."""
    filled = int(round(total_blocks * (percent / 100.0)))
    filled = max(0, min(total_blocks, filled))
    return "█" * filled + "░" * (total_blocks - filled)


def extract_discord_rank_role(member: discord.Member) -> Optional[str]:
    """
    Detect if the user has an allotted Discord rank role:
    Matches 'SSS', 'SS', 'S', 'A', 'B', 'C', 'D' or 'Rank SSS', 'Rank A', etc.
    Returns the highest matching tier.
    """
    detected_tiers = []
    for role in member.roles:
        clean_name = role.name.strip().upper()
        if clean_name.startswith("RANK "):
            clean_name = clean_name.replace("RANK ", "").strip()
        if clean_name in RANK_TIERS:
            detected_tiers.append(clean_name)

    if not detected_tiers:
        return None

    # Return highest tier detected
    detected_tiers.sort(key=lambda t: RANK_TIERS.index(t), reverse=True)
    return detected_tiers[0]


class LevelsCog(commands.Cog, name="Levels"):
    """Discord listener and slash commands for member message activity, letter rank tiers (D..SSS), and shy Ryujin persona."""

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

        # If user leveled up, Ryujin speaks in a shy, 1-line congratulations
        if result["leveled_up"]:
            if result.get("rank_promoted"):
                msg_text = f"...Level {result['level']} and promoted to **Rank {result['rank_tier']}**. *looks away* Don't let it get to your head."
            else:
                msg_text = f"...Congrats on Level {result['level']}. Keep going."

            embed = discord.Embed(
                description=f"<@{user_id}> {msg_text}",
                color=discord.Color.purple(),
            )
            try:
                await message.channel.send(embed=embed)
            except discord.DiscordException:
                pass

    @app_commands.command(name="rank", description="Check your or another member's Hunter rank tier (D, C, B, A, S, SS, SSS)")
    async def rank_cmd(self, interaction: discord.Interaction, member: discord.Member | None = None):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        target = member or interaction.user
        guild_id = interaction.guild.id

        # Sync Discord role if allotted on the server
        discord_tier = extract_discord_rank_role(target) if isinstance(target, discord.Member) else None

        async with async_session_factory() as session:
            service = LevelService(session)
            if discord_tier:
                await service.sync_discord_rank(guild_id=guild_id, user_id=target.id, discord_tier=discord_tier)
                await session.commit()

            card = await service.get_member_rank_card(guild_id=guild_id, user_id=target.id)

        bar = create_progress_bar(card["progress_percent"])

        # Tier-based badge colors
        tier_colors = {
            "D": discord.Color.light_grey(),
            "C": discord.Color.teal(),
            "B": discord.Color.blue(),
            "A": discord.Color.purple(),
            "S": discord.Color.gold(),
            "SS": discord.Color.orange(),
            "SSS": discord.Color.red(),
        }
        color = tier_colors.get(card["rank_tier"], discord.Color.purple())

        embed = discord.Embed(
            title=f"Hunter Rank — {target.display_name}",
            color=color,
            description=f"> *\"{card['shy_quote']}\"*\n\n**Rank Tier:** ⟨ **Rank {card['rank_tier']}** ⟩",
        )
        if target.avatar:
            embed.set_thumbnail(url=target.avatar.url)

        embed.add_field(name="Level", value=str(card["level"]), inline=True)
        embed.add_field(name="Server Rank", value=f"#{card['rank']}", inline=True)
        embed.add_field(name="Messages", value=str(card["messages_count"]), inline=True)

        progress_text = (
            f"`{bar}` {card['progress_percent']}%\n"
            f"{card['current_level_xp']} / {card['xp_needed_for_next']} XP (Total: {card['total_xp']} XP)"
        )
        embed.add_field(name="Level Progress", value=progress_text, inline=False)

        if card.get("previous_rank_tier"):
            embed.set_footer(text=f"Previous Tier: Rank {card['previous_rank_tier']} • Tiers: D → C → B → A → S → SS → SSS")
        else:
            embed.set_footer(text="Tiers: D → C → B → A → S → SS → SSS")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="promote", description="Promote a member to the next or specified rank tier (Officers+)")
    @app_commands.describe(
        member="The member to promote",
        tier="Target rank tier (optional, defaults to next tier)",
        reason="Reason for promotion",
    )
    @app_commands.choices(tier=[
        app_commands.Choice(name="Rank C", value="C"),
        app_commands.Choice(name="Rank B", value="B"),
        app_commands.Choice(name="Rank A", value="A"),
        app_commands.Choice(name="Rank S", value="S"),
        app_commands.Choice(name="Rank SS", value="SS"),
        app_commands.Choice(name="Rank SSS", value="SSS"),
    ])
    async def promote_cmd(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        tier: Optional[str] = None,
        reason: Optional[str] = None,
    ):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        officer_roles = [r.name.lower() for r in interaction.user.roles] if isinstance(interaction.user, discord.Member) else []
        if not (has_sufficient_role(officer_roles, "officer") or interaction.user.guild_permissions.administrator):
            await interaction.response.send_message("Only officers or higher can promote members.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        async with async_session_factory() as session:
            service = LevelService(session)
            try:
                card = await service.promote_member(
                    guild_id=guild_id,
                    officer_id=interaction.user.id,
                    officer_roles=officer_roles,
                    target_user_id=member.id,
                    target_tier=tier,
                    reason=reason,
                )
                await session.commit()
            except (LevelPermissionError, LevelRankError) as e:
                await interaction.response.send_message(f"Error: {e}", ephemeral=True)
                return

        # Try to sync Discord role if matching role exists on the guild
        try:
            old_role = discord.utils.find(lambda r: r.name.upper() in [f"RANK {card['previous_rank_tier']}", card['previous_rank_tier']], interaction.guild.roles)
            new_role = discord.utils.find(lambda r: r.name.upper() in [f"RANK {card['rank_tier']}", card['rank_tier']], interaction.guild.roles)
            if old_role and old_role in member.roles:
                await member.remove_roles(old_role)
            if new_role and new_role not in member.roles:
                await member.add_roles(new_role)
        except discord.DiscordException:
            pass

        embed = discord.Embed(
            title="Rank Promotion",
            color=discord.Color.gold(),
            description=f"> *\"...Promoted <@{member.id}> to **Rank {card['rank_tier']}**. *looks away* Keep working hard.\"*",
        )
        embed.add_field(name="Previous Tier", value=f"Rank {card['previous_rank_tier']}", inline=True)
        embed.add_field(name="New Tier", value=f"Rank {card['rank_tier']}", inline=True)
        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="demote", description="Demote a member to a lower rank tier (Officers+)")
    @app_commands.describe(
        member="The member to demote",
        tier="Target rank tier (optional, defaults to previous tier)",
        reason="Reason for demotion",
    )
    @app_commands.choices(tier=[
        app_commands.Choice(name="Rank D", value="D"),
        app_commands.Choice(name="Rank C", value="C"),
        app_commands.Choice(name="Rank B", value="B"),
        app_commands.Choice(name="Rank A", value="A"),
        app_commands.Choice(name="Rank S", value="S"),
        app_commands.Choice(name="Rank SS", value="SS"),
    ])
    async def demote_cmd(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        tier: Optional[str] = None,
        reason: Optional[str] = None,
    ):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        officer_roles = [r.name.lower() for r in interaction.user.roles] if isinstance(interaction.user, discord.Member) else []
        if not (has_sufficient_role(officer_roles, "officer") or interaction.user.guild_permissions.administrator):
            await interaction.response.send_message("Only officers or higher can demote members.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        async with async_session_factory() as session:
            service = LevelService(session)
            try:
                card = await service.demote_member(
                    guild_id=guild_id,
                    officer_id=interaction.user.id,
                    officer_roles=officer_roles,
                    target_user_id=member.id,
                    target_tier=tier,
                    reason=reason,
                )
                await session.commit()
            except (LevelPermissionError, LevelRankError) as e:
                await interaction.response.send_message(f"Error: {e}", ephemeral=True)
                return

        # Try to sync Discord role
        try:
            old_role = discord.utils.find(lambda r: r.name.upper() in [f"RANK {card['previous_rank_tier']}", card['previous_rank_tier']], interaction.guild.roles)
            new_role = discord.utils.find(lambda r: r.name.upper() in [f"RANK {card['rank_tier']}", card['rank_tier']], interaction.guild.roles)
            if old_role and old_role in member.roles:
                await member.remove_roles(old_role)
            if new_role and new_role not in member.roles:
                await member.add_roles(new_role)
        except discord.DiscordException:
            pass

        embed = discord.Embed(
            title="Rank Demotion",
            color=discord.Color.dark_grey(),
            description=f"> *\"...Demoted <@{member.id}> to **Rank {card['rank_tier']}**. Don't give up, okay?\"*",
        )
        embed.add_field(name="Previous Tier", value=f"Rank {card['previous_rank_tier']}", inline=True)
        embed.add_field(name="New Tier", value=f"Rank {card['rank_tier']}", inline=True)
        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="rankhistory", description="View a member's rank promotion and demotion timeline")
    async def rank_history_cmd(self, interaction: discord.Interaction, member: discord.Member | None = None):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        target = member or interaction.user
        guild_id = interaction.guild.id

        async with async_session_factory() as session:
            service = LevelService(session)
            history = await service.get_rank_history(guild_id=guild_id, user_id=target.id, limit=10)

        embed = discord.Embed(
            title=f"Rank History — {target.display_name}",
            color=discord.Color.purple(),
        )

        if not history:
            embed.description = "...No rank changes recorded yet. Keep active to earn promotions."
        else:
            lines = []
            for h in history:
                icon = "▲" if h["change_type"] == "PROMOTION" else "▼" if h["change_type"] == "DEMOTION" else "●"
                date_str = h["created_at"][:10]
                reason_str = f" — {h['reason']}" if h.get("reason") else ""
                lines.append(f"`{date_str}` **{icon} Rank {h['from_tier']} → {h['to_tier']}** ({h['change_type']}){reason_str}")
            embed.description = "\n".join(lines)

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
            title="Ryujin Community Leaderboard",
            color=discord.Color.gold(),
            description="The most active members in the server!",
        )

        if not leaderboard:
            embed.description = "...No chat activity recorded yet. Start talking in channels to earn XP."
        else:
            lines = []
            for item in leaderboard:
                tier = item.get("rank_tier", "D")
                lines.append(
                    f"**#{item['rank']}** <@{item['discord_user_id']}> — **Rank {tier}** (Level {item['level']}) "
                    f"• {item['total_xp']} XP ({item['messages_count']} msgs)"
                )
            embed.description = "\n".join(lines)

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LevelsCog(bot))
