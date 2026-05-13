"""
Discord bot entry point.

Lives at the repo root so the bot can be launched directly with
`python Connection.py`. All library code is under `src/` and gets
exposed by inserting that directory onto sys.path before any imports
from it. Runtime state goes under `data/`.

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

# Put src/ on sys.path so `from BotConstants import getToken` and
# `load_extension("cogs.X")` resolve to the modules under src/.
sys.path.insert(0, SRC)

# Hidden function that contains the bot secret token.
from BotConstants import getToken  # noqa: E402  (import after sys.path tweak)

import asyncio  # noqa: E402
import logging  # noqa: E402

import discord  # noqa: E402
from discord.ext.commands import Bot, CommandNotFound  # noqa: E402

# Prefix for legacy text commands (e.g. "p!help"). Slash commands ignore this.
prefix = "p!"

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
        # place to push the slash command tree to Discord.
        await self.tree.sync()

    async def on_command_error(self, ctx, error):
        # Suppress "command not found" noise (users typoing the prefix), but
        # log and re-raise anything else so it shows up in output.log.
        if isinstance(error, CommandNotFound):
            return
        logger.error(error)
        raise error

    async def on_message(self, message):
        # Ignore the bot's own messages so it doesn't react to itself.
        if message.author == self.user:
            return
        # Hand off to the prefix-command framework so legacy commands still work.
        await self.process_commands(message)

    async def init_cogs(self):
        # Discover and load every .py file under src/cogs/ as an extension.
        # Failures are logged but don't block other cogs from loading.
        cogs_dir = os.path.join(SRC, "cogs")
        for file in os.listdir(cogs_dir):
            if file.endswith(".py"):
                name = file[:-3]
                try:
                    await self.load_extension(f"cogs.{name}")
                except Exception as e:
                    print(f"Could not load {name} Cog!")
                    logger.error(f"{name} cog failed :")
                    logger.error(e)


async def main():
    # Default intents + message_content so prefix commands can read message text.
    intents = discord.Intents.default()
    intents.message_content = True
    # Custom presence: "Listening to Pekka Bot | prefix".
    listening = discord.Activity(type=discord.ActivityType.listening, name="Pekka Bot | " + prefix)
    client = MyClient(command_prefix=prefix, intents=intents, case_insensitive=True, activity=listening, status=discord.Status.online)
    # `async with client` guarantees a clean shutdown of the gateway connection.
    async with client:
        await client.init_cogs()
        await client.start(getToken())

asyncio.run(main())
