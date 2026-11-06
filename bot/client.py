import argparse
import asyncio
import sys
from typing import Optional

import discord
from discord.ext import commands

from core.config import settings
from core.database import init_db
from core.logger import logger
from core.scheduler import shutdown_scheduler, start_scheduler


def get_ryujin_intents() -> discord.Intents:
    """
    Configure and document Discord Gateway Intents for Ryujin.
    
    1. guilds = True: Required to listen for guild join/leave, guild channel updates, and guild state.
    2. members = True: Privileged intent required to resolve member roles, check permissions,
       track new joins, and auto-provision members upon recruitment approval.
    3. voice_states = True: Required for voice channel activity tracking and event presence monitoring.
    4. message_content = True: Privileged intent explicitly required for Ryujin Brain AI chitchat
       (handling @bot mentions, direct replies, and listening to conversation in designated #chat channels).
    """
    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True
    intents.voice_states = True
    intents.message_content = True
    return intents


class RyujinBot(commands.Bot):
    def __init__(self, dry_run: bool = False, *args, **kwargs):
        intents = kwargs.pop("intents", get_ryujin_intents())
        command_prefix = kwargs.pop("command_prefix", "!")
        super().__init__(command_prefix=command_prefix, intents=intents, *args, **kwargs)
        self.dry_run = dry_run
        self.loaded_cogs_list = []

    async def setup_hook(self) -> None:
        """
        Initializes the database, scheduler, loads cogs, and syncs the application command tree.
        """
        logger.info("Running Ryujin setup_hook...")
        # 1. Initialize DB tables
        await init_db()

        # 2. Start APScheduler
        start_scheduler()

        # 3. Load all feature cogs
        initial_extensions = [
            "bot.cogs.attendance",
            "bot.cogs.events",
            "bot.cogs.recognition",
            "bot.cogs.squads",
            "bot.cogs.recruitment",
            "bot.cogs.tournaments",
            "bot.cogs.moderation",
            "bot.cogs.levels",
            "bot.cogs.wisdom",
            "bot.cogs.ai_chat",
        ]

        for ext in initial_extensions:
            try:
                await self.load_extension(ext)
                self.loaded_cogs_list.append(ext)
                logger.info("Loaded cog extension: %s", ext)
            except commands.ExtensionNotFound:
                # Extension may not be created yet during iterative build
                logger.warning("Extension not yet implemented: %s", ext)
            except Exception as e:
                logger.error("Failed to load extension %s: %s", ext, e, exc_info=True)
                raise

        # 4. Sync slash command tree
        if not self.dry_run:
            try:
                synced = await self.tree.sync()
                logger.info("Synced %d global application command(s).", len(synced))
            except Exception as e:
                logger.warning("Could not sync command tree with Discord gateway (offline or mock): %s", e)
        else:
            logger.info("Dry-run mode active: skipped remote Discord tree.sync(). Local commands registered: %d", len(self.tree.get_commands()))

    async def on_ready(self) -> None:
        logger.info("Ryujin logged in as %s (ID: %s)", self.user, self.user.id if self.user else "N/A")

    async def close(self) -> None:
        shutdown_scheduler()
        await super().close()


async def run_bot(dry_run: bool = False) -> None:
    bot = RyujinBot(dry_run=dry_run)
    if dry_run:
        logger.info("Starting Ryujin in DRY-RUN mode...")
        await bot.setup_hook()
        await bot.close()
        logger.info("Dry-run verification completed successfully. All components booted.")
        return

    logger.info("Starting Ryujin connected to Discord gateway...")
    async with bot:
        await bot.start(settings.DISCORD_TOKEN)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ryujin Discord Bot")
    parser.add_argument("--dry-run", action="store_true", help="Boot everything without connecting to Discord gateway (for CI/tests)")
    args = parser.parse_args()

    try:
        asyncio.run(run_bot(dry_run=args.dry_run))
    except KeyboardInterrupt:
        logger.info("Ryujin stopped by user.")


if __name__ == "__main__":
    main()

