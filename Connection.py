"""
Discord bot entry point.

Lives at the repo root so the bot can be launched directly with
`python Connection.py`. Library code is under `src/`, host-local config
(currently just the token) under `config/`, and runtime state under
`data/`. The two non-stdlib directories are placed on sys.path before
any imports from them.

Responsibilities:
- Build the Bot client with the right intents and presence.
- Auto-load every cog module found in `src/cogs/`.
- Sync the application command tree with Discord on startup.
"""

import os
import sys

# Anchor every path on the directory this file lives in (repo root) rather
# than the process CWD, so the bot launches the same regardless of where
# `python Connection.py` is invoked from.
ROOT = os.path.dirname(os.path.realpath(__file__))
SRC = os.path.join(ROOT, "src")
CONFIG = os.path.join(ROOT, "config")

# Put both directories on sys.path so `from BotConstants import getToken`
# resolves to config/BotConstants.py and `load_extension("cogs.X")` resolves
# to modules under src/cogs/.
sys.path.insert(0, SRC)
sys.path.insert(0, CONFIG)

# Hidden function that contains the bot secret token.
from BotConstants import getToken

import asyncio
import logging

import discord
from discord.ext import commands
from discord.ext.commands import Bot, CommandNotFound

# Optional guild id for instant slash-command propagation. Global syncs
# can take up to an hour to appear in clients; per-guild syncs are
# instant. Set to a guild id (int) to fast-sync to a single server, or
# leave None for global sync.
SYNC_GUILD_ID: int | None = None

# Bot logs go to output.log in the launch directory.
logger = logging.getLogger(__name__)
logging.basicConfig(filename='output.log', filemode='w', format='%(name)s - %(levelname)s - %(message)s')


class MyClient(Bot):
    """Bot subclass with custom lifecycle hooks and a global command-error filter."""

    async def on_ready(self):
        # Fires every time the gateway connection is (re)established.
        print(f"We have logged in as {self.user}")

    async def setup_hook(self) -> None:
        # Runs once before the bot starts receiving events. This is the right
        # place to push the slash command tree to Discord. Per-guild sync
        # propagates instantly; global sync can take up to an hour.
        if SYNC_GUILD_ID is not None:
            guild = discord.Object(id=SYNC_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_command_error(self, ctx, error):
        # The bot is slash-only, but if anyone @mentions it with random text
        # the command framework may raise CommandNotFound. Suppress that one
        # noise case and log everything else so real bugs show up in
        # output.log.
        if isinstance(error, CommandNotFound):
            return
        logger.error(error)
        raise error

    async def init_cogs(self):
        # Discover and load every .py file under src/cogs/ as an extension.
        # Files starting with `_` (e.g. __init__.py, _helpers.py) are skipped
        # so support modules aren't accidentally loaded as cogs.
        # Failures are logged but don't block other cogs from loading.
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
    # Default intents are enough for slash-only operation; the privileged
    # message_content intent isn't requested.
    intents = discord.Intents.default()
    # Custom presence: "Listening to Pekka Bot".
    listening = discord.Activity(type=discord.ActivityType.listening, name="Pekka Bot")
    # command_prefix is required by Bot() but no prefix commands exist —
    # when_mentioned makes the bot only listen for prefix commands when
    # @mentioned, which is effectively inert with an empty command set.
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
        await client.start(getToken())

asyncio.run(main())
