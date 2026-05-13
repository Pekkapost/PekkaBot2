"""
Auto-generated help cog.

Discovers every cog loaded into the bot and lists their commands
(both slash and prefix) in a single embed. Use `/help` for the overview
or `/help cog:<name>` to focus on one cog. The cog parameter has
autocomplete sourced from the live cog registry, so the list always
stays in sync without hard-coding anything.
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional


def _slash_summary(cmd):
    """One-line summary of a slash command: `/qualified.name — description`."""
    return f"`/{cmd.qualified_name}` — {cmd.description or 'No description.'}"


def _prefix_summary(cmd, prefix):
    """One-line summary of a prefix command, including any aliases."""
    aliases = f" (aliases: {', '.join(cmd.aliases)})" if cmd.aliases else ""
    return f"`{prefix}{cmd.qualified_name}`{aliases} — {cmd.brief or cmd.help or 'No description.'}"


class Help(commands.Cog):
    """Cog providing the auto-discovery `/help` slash command."""

    def __init__(self, client):
        self.client = client

    async def cog_autocomplete(self, interaction: discord.Interaction, current: str):
        """Autocomplete for the `cog` argument — substring-match against loaded cog names."""
        return [
            app_commands.Choice(name=name, value=name)
            for name in self.client.cogs
            if current.lower() in name.lower()
        ][:25]  # Discord caps autocomplete at 25 entries.

    @app_commands.command(name="help", description="Show available commands.")
    @app_commands.describe(cog="Optionally narrow the listing to a single cog.")
    @app_commands.autocomplete(cog=cog_autocomplete)
    async def help_cmd(self, interaction: discord.Interaction, cog: Optional[str] = None):
        # command_prefix is normally a string for this bot but discord.py allows
        # callables too; only use it as a string when it actually is one.
        prefix_str = self.client.command_prefix if isinstance(self.client.command_prefix, str) else ""

        if cog is not None:
            target = self.client.get_cog(cog)
            if target is None:
                await interaction.response.send_message(f"No cog named `{cog}`.", ephemeral=True)
                return
            embed = self._build_embed([target], prefix_str, title=f"{cog} Commands")
        else:
            embed = self._build_embed(list(self.client.cogs.values()), prefix_str, title="Available Commands")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    def _build_embed(self, cogs, prefix_str, title):
        """Render one embed field per cog, listing its slash and prefix commands."""
        embed = discord.Embed(title=title, color=discord.Color.blurple())
        for c in cogs:
            lines = []
            # walk_app_commands yields every slash command including groups; skip
            # groups themselves since they aren't invokable, only their leaves are.
            for cmd in c.walk_app_commands():
                if isinstance(cmd, app_commands.Group):
                    continue
                lines.append(_slash_summary(cmd))
            for cmd in c.get_commands():
                lines.append(_prefix_summary(cmd, prefix_str))
            if lines:
                # Discord caps field values at 1024 chars — fine for this bot's
                # current command count, but worth a longer-term split if a cog
                # ever grows past ~20 commands.
                embed.add_field(name=c.qualified_name, value="\n".join(lines), inline=False)
        if not embed.fields:
            embed.description = "No commands found."
        return embed


async def setup(client):
    # discord.py extension entry point — called by `bot.load_extension`.
    await client.add_cog(Help(client))
