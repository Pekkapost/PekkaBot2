"""
Discord bot entry point.

Lives at the repo root so the bot can be launched directly with
`python Connection.py`.

Responsibilities:
- Build the Bot client with the right intents and presence.
- Auto-load every cog module found in `src/cogs/`.
- Sync the application command tree with Discord on startup.
"""

import os
import sys

# Anchor every path on the directory this file lives in (repo root) rather than the process CWD.
ROOT = os.path.dirname(os.path.realpath(__file__))
SRC = os.path.join(ROOT, "src")
CONFIG = os.path.join(ROOT, "config")
sys.path.insert(0, SRC)
sys.path.insert(0, CONFIG)

# Hidden function that contains the bot secret token.
from BotConstants import get_token

import asyncio
import logging

import discord
from discord.ext import commands
from discord.ext.commands import Bot, CommandNotFound

SYNC_GUILD_ID: int | None = None

# Bot logs go to output.log in the launch directory.
logger = logging.getLogger(__name__)
logging.basicConfig(
    filename="output.log",
    filemode="w",
    format="%(name)s - %(levelname)s - %(message)s",
)


class MyClient(Bot):
    """Bot subclass with custom lifecycle hooks and a global command-error filter."""

    async def on_ready(self):
        # Fires every time the gateway connection is (re)established.
        print(f"We have logged in as {self.user}")

    async def setup_hook(self) -> None:
        # Runs once before the bot starts receiving events.
        if SYNC_GUILD_ID is not None:
            guild = discord.Object(id=SYNC_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_command_error(self, ctx, error):
        # Ignore CommandNotFound errors raised when a user tries to invoke a
        # command that doesn't exist (e.g. random @mention text the bot
        # picked up via commands.when_mentioned).
        if isinstance(error, CommandNotFound):
            return
        logger.exception("Unhandled command error", exc_info=error)
        raise error

    async def init_cogs(self):
        # Discover and load every .py file under src/cogs/ as an extension.
        # Files starting with `_` (e.g. __init__.py, _helpers.py) are skipped.
        # Failures are logged (with traceback) but don't block other cogs.
        cogs_dir = os.path.join(SRC, "cogs")
        for file in os.listdir(cogs_dir):
            if file.endswith(".py") and not file.startswith("_"):
                name = file[:-3]
                try:
                    await self.load_extension(f"cogs.{name}")
                except Exception:
                    logger.exception("Failed to load cog %s", name)


async def main():
    # Custom presence: "Listening to Pekka Bot".
    listening = discord.Activity(type=discord.ActivityType.listening, name="Pekka Bot")
    # We currently do not use prefix commands, but we need to set a non-empty
    # prefix to initialize the Bot. when_mentioned makes the dispatcher only
    # look at @mentions, which is inert with no prefix commands registered.
    client = MyClient(
        command_prefix=commands.when_mentioned,
        intents=discord.Intents.default(),
        case_insensitive=True,
        activity=listening,
        status=discord.Status.online,
    )
    # `async with client` guarantees a clean shutdown of the gateway connection.
    async with client:
        await client.init_cogs()
        try:
            await client.start(get_token())
        except discord.LoginFailure:
            print(
                "Discord rejected the token. Check `TOKEN` in "
                "config/BotConstants.py — copy a fresh value from "
                "your application's Bot → Token tab."
            )
            return

asyncio.run(main())
