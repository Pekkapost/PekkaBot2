import discord
from discord import app_commands
from discord.ext import commands
from typing import List
import os
import json

cwd = os.path.dirname(os.path.realpath(__file__))
with open(cwd + "/../Database.json") as dataFile:
    database = json.load(dataFile)

CHARACTER_ALIASES = {
    "captain": ["gran", "djeeta"],
}


def _make_character_command(name, aliases):
    help_text = database["characters"][name]["help"]

    @commands.command(name=name, aliases=aliases, help=help_text, brief=help_text)
    async def _cmd(self, ctx):
        await ctx.send(embed=self.getEmbed(name, "guide"))
        await ctx.send(embed=self.getEmbed(name, "channel"))

    return _cmd


class Characters(commands.Cog):
    def __init__(self, client):
        self.client = client

    def getEmbed(self, character, charType):
        data = database["characters"][character]
        charThread = data[charType]
        if charThread == "":
            charDescription = "No guide exists"
        else:
            charDescription = f"Click [here]({charThread}) to go to {charType.capitalize()}"
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
        return [
            app_commands.Choice(name=char.capitalize(), value=char)
            for char in database["characters"]
            if current.lower() in char.lower()
        ][:25]

    @app_commands.command(
        name="guide",
        description="This command will provide some of the community guide for specified character.",
    )
    @app_commands.describe(character="The character of your choice")
    @app_commands.autocomplete(character=char_autocomplete)
    async def get_character(self, interaction: discord.Interaction, character: str):
        if character not in database["characters"]:
            await interaction.response.send_message(content=f"{character} is not supported.")
            return
        await interaction.response.send_message(
            embeds=[self.getEmbed(character, "guide"), self.getEmbed(character, "channel")]
        )

    # Generate one prefix command per character. Mutating locals() inside the
    # class body adds attributes that CogMeta picks up as commands.
    for _char in database["characters"]:
        locals()[_char] = _make_character_command(_char, CHARACTER_ALIASES.get(_char, []))
    del _char


async def setup(client):
    await client.add_cog(Characters(client))
