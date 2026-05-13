"""
Custom help command (work in progress).

Wraps discord.py's DefaultHelpCommand so the auto-generated help text is
delivered as a single embed instead of plain code blocks.

Not currently wired into the bot — Connection.py only auto-loads modules
under src/cogs/. To enable, instantiate this class and assign it to the
bot's `help_command` attribute (e.g. `bot.help_command = MyHelpCommand()`).
"""

import discord
from discord.ext import commands


class MyHelpCommand(commands.DefaultHelpCommand):
    """DefaultHelpCommand override that re-renders the paginated output as one embed."""

    async def send_pages(self):
        # `self.paginator` already contains the formatted help text split into
        # Discord-sized pages; we glue them back together into a single embed
        # description rather than sending one message per page.
        destination = self.get_destination()
        e = discord.Embed(title="WIP Menu", color=discord.Color.blurple(), description="")

        for page in self.paginator.pages:
            e.description += page

        await destination.send(embed=e)
