from BotConstants import getToken
import discord
from discord.ext.commands import Bot, CommandNotFound
from discord.ext import tasks
import os
import json
import asyncio
import itertools
import logging
from datetime import datetime, timezone

cwd = os.path.dirname(os.path.realpath(__file__))

prefix = "p!"

logger = logging.getLogger(__name__)
logging.basicConfig(filename='output.log', filemode='w', format='%(name)s - %(levelname)s - %(message)s')


class MyClient(Bot):
    async def on_ready(self):
        print(f"We have logged in as {self.user}")

    async def setup_hook(self) -> None:
        await self.tree.sync()

    async def on_command_error(self, ctx, error):
        if isinstance(error, CommandNotFound):
            return
        logger.error(error)
        raise error

    async def on_message(self, message):
        if message.author == self.user:
            return
        # if message.channel.id in threadList and message.channel.type == discord.ChannelType.text:
        #     if any(role in pingRoles for role in message.raw_role_mentions):
        #         await message.add_reaction(emoteThread)
        await self.process_commands(message)

    async def init_cogs(self):
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
    intents = discord.Intents.default()
    intents.message_content = True
    listening = discord.Activity(type=discord.ActivityType.listening, name="Narmaya Bot | " + prefix)
    client = MyClient(command_prefix=prefix, intents=intents, case_insensitive=True, activity=listening, status=discord.Status.online)
    async with client:
        await client.init_cogs()
        await client.start(getToken())

asyncio.run(main())
