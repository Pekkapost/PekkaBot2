from typing import List
import discord
from discord import app_commands
from discord.ext import commands
import json
import os

cwd = os.path.dirname(os.path.realpath(__file__))
with open(cwd + "/../Database.json") as dataFile:
    database = json.load(dataFile)

# (command_name, faq_data_key, aliases)
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
    help_text = database["faqdata"][faq_key]["help"]

    @commands.command(name=command_name, aliases=aliases, help=help_text, brief=help_text)
    async def _cmd(self, ctx):
        await ctx.send(embed=self.getEmbed(faq_key))

    return _cmd


class Menu(commands.Cog):
    def __init__(self, client):
        self.client = client

    def getEmbed(self, item):
        data = database["faqdata"][item]
        embed = discord.Embed(
            title=data["title"],
            url=data.get("link", ""),
            description=data["data"],
            color=0xa0a0ff,
        )
        embed.set_thumbnail(url=data.get("image", ""))
        return embed

    async def topic_autocomplete(self, interaction: discord.Interaction, current: str) -> List[app_commands.Choice[str]]:
        options = []
        for key, entry in database["faqdata"].items():
            name = entry["title"]
            if current.lower() in name.lower():
                options.append(app_commands.Choice(name=name.capitalize(), value=key))
        return options[:25]

    @app_commands.command(
        name="faq",
        description="This command will provide some of the FAQ you might want to know.",
    )
    @app_commands.describe(topic="The topic of your choice")
    @app_commands.autocomplete(topic=topic_autocomplete)
    async def get_faq(self, interaction: discord.Interaction, topic: str):
        if topic not in database["faqdata"]:
            await interaction.response.send_message(content=f"{topic} is not supported.")
            return
        await interaction.response.send_message(embeds=[self.getEmbed(topic)])

    @commands.command(
        aliases=["pin"],
        help=database["faqdata"]["pins"]["help"],
        brief=database["faqdata"]["pins"]["help"],
    )
    async def pins(self, ctx):
        await ctx.send("Read the Pins")

    # Generate one prefix command per FAQ entry. Mutating locals() inside the
    # class body adds attributes that CogMeta picks up as commands.
    for _name, _key, _aliases in FAQ_COMMANDS:
        locals()[_name] = _make_faq_command(_name, _key, _aliases)
    del _name, _key, _aliases


async def setup(client):
    await client.add_cog(Menu(client))
