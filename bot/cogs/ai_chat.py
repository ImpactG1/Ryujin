import discord
from discord import app_commands
from discord.ext import commands

from core.database import async_session_factory
from services.ai_service import AIService


class AIChatCog(commands.Cog, name="AIChat"):
    """Discord listener and slash commands for Groq-powered Ryujin Brain AI."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    ai_group = app_commands.Group(name="ai", description="Ryujin Brain Groq AI commands")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore own messages or bot messages
        if message.author.bot:
            return

        # Check if bot was @mentioned or replied to
        is_mentioned = self.bot.user in message.mentions if self.bot.user else False
        is_reply = False
        if message.reference and message.reference.resolved:
            if getattr(message.reference.resolved, "author", None) == self.bot.user:
                is_reply = True

        if is_mentioned or is_reply:
            guild_id = message.guild.id if message.guild else 0
            # Clean mention from text
            clean_content = message.content.replace(f"<@{self.bot.user.id}>", "").strip() if self.bot.user else message.content

            async with message.channel.typing():
                async with async_session_factory() as session:
                    ai_service = AIService(session)
                    reply = await ai_service.chat(
                        channel_id=message.channel.id,
                        user_id=message.author.id,
                        guild_id=guild_id,
                        user_message=clean_content or "Hello Ryujin!",
                    )
                    await session.commit()

            await message.reply(reply)

    @app_commands.command(name="ryujin", description="Speak directly with Ryujin (Groq-powered AI Brain)")
    @app_commands.describe(prompt="What would you like to ask or say to Ryujin?")
    async def ryujin_cmd(self, interaction: discord.Interaction, prompt: str):
        """Natural top-level /ryujin command to chat with Ryujin Brain."""
        await interaction.response.defer()
        guild_id = interaction.guild.id if interaction.guild else 0

        async with async_session_factory() as session:
            ai_service = AIService(session)
            reply = await ai_service.chat(
                channel_id=interaction.channel_id or 0,
                user_id=interaction.user.id,
                guild_id=guild_id,
                user_message=prompt,
            )
            await session.commit()

        await interaction.followup.send(reply)

    @ai_group.command(name="chat", description="Chat directly with Ryujin Brain")
    async def chat_cmd(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        guild_id = interaction.guild.id if interaction.guild else 0

        async with async_session_factory() as session:
            ai_service = AIService(session)
            reply = await ai_service.chat(
                channel_id=interaction.channel_id or 0,
                user_id=interaction.user.id,
                guild_id=guild_id,
                user_message=query,
            )
            await session.commit()

        await interaction.followup.send(reply)

    @ai_group.command(name="summary", description="Generate an AI-powered community metrics digest")
    async def summary_cmd(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        await interaction.response.defer()
        guild_id = interaction.guild.id

        async with async_session_factory() as session:
            ai_service = AIService(session)
            digest = await ai_service.generate_community_summary(guild_id)

        embed = discord.Embed(
            title="Ryujin Community AI Digest",
            color=discord.Color.blue(),
            description=digest,
        )
        embed.set_footer(text="Powered by Groq LLM & Real Server Metrics")
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AIChatCog(bot))
