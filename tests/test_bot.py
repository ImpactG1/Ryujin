import pytest
from bot.client import RyujinBot, get_ryujin_intents, run_bot
from core.scheduler import scheduler


@pytest.mark.asyncio
async def test_bot_intents():
    """Verify that all required intents are configured with appropriate permissions."""
    intents = get_ryujin_intents()
    assert intents.guilds is True, "Guilds intent must be True"
    assert intents.members is True, "Members intent must be True"
    assert intents.voice_states is True, "Voice states intent must be True"
    assert intents.message_content is True, "Message content intent must be True for AI chat layer"
    # Ensure docstring explains rationale
    assert "privileged" in get_ryujin_intents.__doc__.lower()
    assert "ai chitchat" in get_ryujin_intents.__doc__.lower()


@pytest.mark.asyncio
async def test_bot_dry_run_startup():
    """Verify that dry-run mode initializes DB, scheduler, loads all cogs without connecting to Discord."""
    bot = RyujinBot(dry_run=True)
    assert bot.dry_run is True

    await bot.setup_hook()

    # Verify all expected extensions are loaded
    expected_cogs = [
        "bot.cogs.attendance",
        "bot.cogs.events",
        "bot.cogs.recognition",
        "bot.cogs.squads",
        "bot.cogs.recruitment",
        "bot.cogs.tournaments",
        "bot.cogs.moderation",
        "bot.cogs.ai_chat",
    ]
    for cog_name in expected_cogs:
        assert cog_name in bot.loaded_cogs_list, f"Expected {cog_name} to be loaded"

    # Verify scheduler started
    assert scheduler.running is True

    # Clean shutdown
    await bot.close()


@pytest.mark.asyncio
async def test_run_bot_dry_run_function():
    """Verify the high-level run_bot dry-run entrypoint completes without exception."""
    await run_bot(dry_run=True)

