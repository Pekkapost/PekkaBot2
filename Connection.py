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

# Anchor every path on the directory this file lives in (repo root) rather than the process CWD
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
    filename='output.log',
    filemode='w',
    format='%(name)s - %(levelname)s - %(message)s',
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
        # Ignores CommandNotFound errors which are raised when a user tries to invoke a
        # command that doesnt exist.
        if isinstance(error, CommandNotFound):
            return
        logger.error(error)
        raise error

    async def init_cogs(self):
        # Discover and load every .py file under src/cogs/ as an extension.
        # Files starting with `_` (e.g. __init__.py, _helpers.py) are skipped.
        cogs_dir = os.path.join(SRC, "cogs")
        for file in os.listdir(cogs_dir):
            if file.endswith(".py") and not file.startswith("_"):
                name = file[:-3]
                try:
                    await self.load_extension(f"cogs.{name}")
                except Exception as e:
                    print(f"Could not load {name} Cog!")
                    logger.error(f"{name} cog failed :")
                    logger.error(e)


async def main():
    # Default intents are enough.
    intents = discord.Intents.default()
    # Custom presence: "Listening to Pekka Bot".
    listening = discord.Activity(type=discord.ActivityType.listening, name="Pekka Bot")
    # We currently do not use prefix commands, but we need to set a non-empty prefix to
    # initialize the Bot.
    client = MyClient(
        command_prefix=commands.when_mentioned,
        intents=intents,
        case_insensitive=True,
        activity=listening,
        status=discord.Status.online,
    )
    # `async with client` guarantees a clean shutdown of the gateway connection.
    async with client:
        await client.init_cogs()
        await client.start(get_token())

asyncio.run(main())
