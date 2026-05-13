"""
Invite link cog.

Exposes a single slash command, /invite, that posts the bot's OAuth2
invite URL so users can re-invite the bot to other servers without
having to dig through the Developer Portal.

The URL itself lives in config/BotConstants.py (gitignored) so the
cog stays deployment-agnostic and the link can be rotated without
touching source code.
"""

import discord
from discord import app_commands
from discord.ext import commands

from BotConstants import get_invite_url


class Invite(commands.Cog):
    """Cog providing the /invite slash command."""

    def __init__(self, client):
        self.client = client

    @app_commands.command(name="invite", description="Get a link to invite the bot to your server.")
    async def invite(self, interaction: discord.Interaction):
        # Re-read the URL on every invocation so editing config/BotConstants.py and reloading the cog
        # (without a full restart) picks up the change.
        url = get_invite_url()
        # If the URL hasn't been filled in yet, send an ephemeral error message instead of a broken link.
        if not url:
            await interaction.response.send_message(
                "Invite URL is not configured. Set `INVITE_URL` in `config/BotConstants.py` and restart the bot.",
                ephemeral=True,
            )
            return
        # Public (non-ephemeral) so others in the channel can also click the link.
        await interaction.response.send_message(f"Invite me to your server: {url}")


async def setup(client):
    # discord.py extension entry point — called by `bot.load_extension`.
    await client.add_cog(Invite(client))
