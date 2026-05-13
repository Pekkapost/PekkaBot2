"""
FAQ menu cog.

Exposes one prefix command per FAQ topic (with friendly aliases) and a
single `/faq topic:<name>` slash command. Each command posts an embed
sourced from Database.json's `faqdata` section.

The per-topic prefix commands are generated dynamically from the
FAQ_COMMANDS config below so adding a new FAQ entry only requires editing
this list and Database.json.
"""

from typing import List
import discord
from discord import app_commands
from discord.ext import commands
import json
import os

# Database lives at the repo root one level up from the cogs/ directory.
cwd = os.path.dirname(os.path.realpath(__file__))
with open(cwd + "/../Database.json") as dataFile:
    database = json.load(dataFile)

# (command_name, faq_data_key, aliases)
# command_name is what users type (e.g. p!sigil_drop_table); faq_data_key is
# the key under database["faqdata"]; aliases are extra invocations.
FAQ_COMMANDS = [
    ("sigil_drop_table", "sigildrops", ["sigildroptable", "sigil_drop", "sigildrop"]),
    ("afk", "afk", []),
    ("damage_calculator", "calculator", ["damagecalculator", "calculator", "calc", "damagecalc", "dmgcalc"]),
    ("quest_rate_table", "questdrops", ["questratetabe", "questrate", "quest_rate", "questdrops", "quest_drops"]),
    ("curio_drop_table", "curiodrops", ["curiodroptable", "curio_drop", "curiodrop"]),
    ("dps_meter", "dpsmeter", ["dpsmeter", "dps", "skill_issue", "skillissue"]),
    ("damage_cap", "damagecap", ["damagecap", "dmgcap", "cap"]),
    ("awakening", "awakening", []),
]


def _make_faq_command(command_name, faq_key, aliases):
    """
    Build a discord.py Command callable that posts the FAQ embed for `faq_key`.

    Help/brief text is pulled from the FAQ entry so all command metadata
    stays alongside the data.
    """
    help_text = database["faqdata"][faq_key]["help"]

    @commands.command(name=command_name, aliases=aliases, help=help_text, brief=help_text)
    async def _cmd(self, ctx):
        await ctx.send(embed=self.getEmbed(faq_key))

    return _cmd


class Menu(commands.Cog):
    """Cog that registers a prefix command per FAQ topic plus a `/faq` slash command."""

    def __init__(self, client):
        self.client = client

    def getEmbed(self, item):
        """Build a Discord embed for an FAQ entry. Optional fields (link, image) default to empty."""
        data = database["faqdata"][item]
        embed = discord.Embed(
            title=data["title"],
            url=data.get("link", ""),
            description=data["data"],
            # Hard-coded brand color (light blue/purple) shared across all FAQ embeds.
            color=0xa0a0ff,
        )
        embed.set_thumbnail(url=data.get("image", ""))
        return embed

    async def topic_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        """Autocomplete callback for /faq — matches against the human-readable `title` field."""
        options = []
        for key, entry in database["faqdata"].items():
            name = entry["title"]
            if current.lower() in name.lower():
                options.append(app_commands.Choice(name=name.capitalize(), value=key))
        return options[:25]  # Discord caps autocomplete at 25 entries.

    @app_commands.command(
        name="faq",
        description="This command will provide some of the FAQ you might want to know.",
    )
    @app_commands.describe(topic="The topic of your choice")
    @app_commands.autocomplete(topic=topic_autocomplete)
    async def get_faq(self, interaction: discord.Interaction, topic: str):
        """Slash command implementation of the per-topic FAQ commands."""
        if topic not in database["faqdata"]:
            await interaction.response.send_message(content=f"{topic} is not supported.")
            return
        await interaction.response.send_message(embeds=[self.getEmbed(topic)])

    # `pins` is hand-written because it doesn't fit the embed pattern — it
    # just nudges the user to read the channel's pinned messages.
    @commands.command(
        aliases=["pin"],
        help=database["faqdata"]["pins"]["help"],
        brief=database["faqdata"]["pins"]["help"],
    )
    async def pins(self, ctx):
        await ctx.send("Read the Pins")

    # ------------------------------------------------------------------
    # Dynamic per-FAQ prefix commands.
    #
    # CogMeta inspects the class __dict__ at class-creation time looking for
    # _BaseCommand instances. Mutating locals() inside the class body adds
    # entries to that namespace dict before the metaclass runs, so each
    # generated command is picked up just like a hand-written method.
    # ------------------------------------------------------------------
    for _name, _key, _aliases in FAQ_COMMANDS:
        locals()[_name] = _make_faq_command(_name, _key, _aliases)
    del _name, _key, _aliases


async def setup(client):
    # discord.py extension entry point — called by `bot.load_extension`.
    await client.add_cog(Menu(client))
