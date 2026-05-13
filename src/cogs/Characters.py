"""
Character guide cog.

Exposes one prefix command per character (e.g. `p!narmaya`) and one slash
command `/guide character:<name>`. Each command posts two embeds: the
guide link and the discussion-channel link, sourced from Database.json.

The per-character commands are generated dynamically in the class body so
that adding a character to Database.json automatically creates a command
without code changes.
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import List
import os
import json

# Database lives at the repo root one level up from the cogs/ directory.
cwd = os.path.dirname(os.path.realpath(__file__))
with open(cwd + "/../Database.json") as dataFile:
    database = json.load(dataFile)

# Aliases for prefix commands. Only characters that need aliases are listed;
# everything else gets just its canonical name.
CHARACTER_ALIASES = {
    "captain": ["gran", "djeeta"],
}


def _make_character_command(name, aliases):
    """
    Build a discord.py Command callable for a single character.

    The callable, when invoked, sends the guide embed and the channel embed
    to the channel the message arrived in. Help/brief text is pulled from
    Database.json so all command metadata stays in one place.
    """
    help_text = database["characters"][name]["help"]

    @commands.command(name=name, aliases=aliases, help=help_text, brief=help_text)
    async def _cmd(self, ctx):
        await ctx.send(embed=self.getEmbed(name, "guide"))
        await ctx.send(embed=self.getEmbed(name, "channel"))

    return _cmd


class Characters(commands.Cog):
    """Cog that registers a prefix command per character plus a `/guide` slash command."""

    def __init__(self, client):
        self.client = client

    def getEmbed(self, character, charType):
        """
        Build a Discord embed for a character's guide or discussion channel.

        `charType` is the JSON field name ("guide" or "channel"). If the field
        is empty the embed shows a "no guide exists" placeholder rather than
        a broken link.
        """
        data = database["characters"][character]
        charThread = data[charType]
        if charThread == "":
            charDescription = "No guide exists"
        else:
            charDescription = f"Click [here]({charThread}) to go to {charType.capitalize()}"
        # Color is stored as a hex string (e.g. "0xff0000") so int(.., 0) auto-detects the base.
        charColor = int(data["color"], 0)
        embed = discord.Embed(
            title=f"{character.capitalize()} {charType.capitalize()}",
            url=charThread,
            description=charDescription,
            color=charColor,
        )
        if "image" in data:
            embed.set_thumbnail(url=data["image"])
        return embed

    async def char_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete callback for /guide — substring-matches the user's typed text against character keys."""
        return [
            app_commands.Choice(name=char.capitalize(), value=char)
            for char in database["characters"]
            if current.lower() in char.lower()
        ][:25]  # Discord caps autocomplete at 25 entries.

    @app_commands.command(
        name="guide",
        description="This command will provide some of the community guide for specified character.",
    )
    @app_commands.describe(character="The character of your choice")
    @app_commands.autocomplete(character=char_autocomplete)
    async def get_character(self, interaction: discord.Interaction, character: str):
        """Slash command implementation of the per-character guide commands."""
        if character not in database["characters"]:
            await interaction.response.send_message(content=f"{character} is not supported.")
            return
        await interaction.response.send_message(
            embeds=[self.getEmbed(character, "guide"), self.getEmbed(character, "channel")]
        )

    # ------------------------------------------------------------------
    # Dynamic per-character prefix commands.
    #
    # CogMeta inspects the class __dict__ at class-creation time looking for
    # _BaseCommand instances. Mutating locals() inside the class body adds
    # entries to that namespace dict before the metaclass runs, so each
    # generated command is picked up just like a hand-written method.
    # ------------------------------------------------------------------
    for _char in database["characters"]:
        locals()[_char] = _make_character_command(_char, CHARACTER_ALIASES.get(_char, []))
    del _char


async def setup(client):
    # discord.py extension entry point — called by `bot.load_extension`.
    await client.add_cog(Characters(client))
