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
with open(cwd + "/GBFRdiscord.json") as varFile:
    varData = json.load(varFile)

threadList = varData["threadList"]
prefix = varData["prefix"]
pingRoles = varData["pingRoles"]
emoteThread = varData["emoteThread"]
whitelist = varData["whitelist"]

logger = logging.getLogger(__name__)
logging.basicConfig(filename='output.log', filemode='w', format='%(name)s - %(levelname)s - %(message)s')


class MyClient(Bot):
    async def on_ready(self):
        print(f"We have logged in as {self.user}")

    async def setup_hook(self) -> None:
        self.thread_cleanup.start()
        await self.tree.sync()

    async def on_command_error(self, ctx, error):
        if isinstance(error, CommandNotFound):
            return
        logger.error(error)
        raise error

    # Auto-create LFG threads when a user reacts with the configured emote
    async def on_raw_reaction_add(self, payload):
        if payload.member.bot:
            return
        if str(payload.emoji) != emoteThread:
            return
        message = await self.get_channel(payload.channel_id).fetch_message(payload.message_id)
        mentions = message.raw_role_mentions
        foundMention = any(role in pingRoles for role in mentions)
        if not foundMention:
            return
        messageContent = message.content
        for roleMention in mentions:
            messageContent = messageContent.replace(f"<@&{roleMention}>", "")
        title = (message.author.name + "`s " + messageContent)[:80]
        await message.create_thread(name=title, auto_archive_duration=60)

    async def on_message(self, message):
        if message.author == self.user:
            return
        if message.channel.id in threadList and message.channel.type == discord.ChannelType.text:
            if any(role in pingRoles for role in message.raw_role_mentions):
                await message.add_reaction(emoteThread)
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

    @tasks.loop(hours=1)
    async def thread_cleanup(self):
        for channel_id in threadList:
            try:
                currentChannel = await self.fetch_channel(channel_id)
            except Exception:
                continue
            archivedThreads = [t async for t in currentChannel.archived_threads()]
            for thread in itertools.chain(currentChannel.threads, archivedThreads):
                if thread.id in whitelist:
                    print(f"Skipping: {thread.id}")
                    continue
                try:
                    messages = [m async for m in thread.history(limit=1)]
                    age = datetime.now(timezone.utc) - messages[0].created_at
                    if age.total_seconds() > 3600:
                        await thread.delete()
                except Exception as e:
                    print("Could not find message in thread")
                    logger.error(f"Trying to find {thread.last_message_id}")
                    logger.error(e)

    @thread_cleanup.before_loop
    async def before_my_task(self):
        await self.wait_until_ready()


async def main():
    intents = discord.Intents.default()
    intents.message_content = True
    listening = discord.Activity(type=discord.ActivityType.listening, name="Narmaya Bot | " + prefix)
    client = MyClient(command_prefix=prefix, intents=intents, case_insensitive=True, activity=listening, status=discord.Status.online)
    async with client:
        await client.init_cogs()
        await client.start(getToken())

asyncio.run(main())
