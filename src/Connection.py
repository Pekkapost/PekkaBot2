"""
Discord bot entry point.

Responsibilities:
- Build the Bot client with the right intents and presence.
- Auto-load every cog module found in `src/cogs/`.
- Sync the application command tree with Discord on startup.
"""

# Hidden function that contains the bot secret token
from BotConstants import getToken

import discord
from discord.ext.commands import Bot, CommandNotFound
import os
import asyncio
import logging

# Absolute path of the directory this file lives in. Used as the anchor for
# locating sibling resources (cogs/, JSON data files) without depending on the
# process CWD.
cwd = os.path.dirname(os.path.realpath(__file__))

# Prefix for legacy text commands (e.g. "p!help"). Slash commands ignore this.
prefix = "p!"

# Bot logs go to output.log next to wherever the bot is launched from.
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
        for file in os.listdir(f"{cwd}/cogs"):
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
