"""
Recurring weekly reminders cog.

Exposes a `/reminder` slash command group with four subcommands:
  add     — schedule a recurring reminder (channel, weekday, HH:MM, lead, msg)
  list    — list all reminders (ephemeral)
  test    — fire a reminder immediately without affecting its schedule
  remove  — delete a reminder by id

When fired the bot posts the message followed by a Discord relative
timestamp (`<t:UNIX:R>`) computed from `lead_minutes` after the fire time,
so a 120-minute lead renders as "in 2 hours" in the user's local timezone.

State is persisted in `src/Reminders.json` so reminders survive restarts.
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timedelta

# Python's datetime.weekday() returns 0=Monday..6=Sunday; index aligns with this list.
WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WEEKDAY_CHOICES = [app_commands.Choice(name=n, value=i) for i, n in enumerate(WEEKDAY_NAMES)]

# Persisted state lives at <repo>/src/Reminders.json (one level up from cogs/).
DATA_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "Reminders.json")


def _load_data():
    """Read the persisted reminder list, returning a fresh empty structure if the file is missing."""
    if not os.path.exists(DATA_PATH):
        return {"reminders": [], "next_id": 1}
    with open(DATA_PATH) as f:
        return json.load(f)


def _save_data(data):
    """Persist the reminder list to disk. Called after every state-modifying operation."""
    with open(DATA_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _format_reminder(r):
    """One-line summary of a reminder used by /reminder list."""
    return (
        f"`#{r['id']}` <#{r['channel_id']}> — "
        f"{WEEKDAY_NAMES[r['weekday']]} {r['hour']:02d}:{r['minute']:02d} "
        f"(lead {r['lead_minutes']}m): {r['message']!r}"
    )


class Reminders(commands.Cog):
    """Cog that registers the /reminder command group and runs the periodic fire loop."""

    def __init__(self, client):
        self.client = client
        # Load persisted reminders into memory at construction. All reads/writes
        # happen against this dict; the disk file is only touched on save.
        self.data = _load_data()

    async def cog_load(self):
        # discord.py 2.x lifecycle hook — start the background loop after the
        # cog has been fully attached to the bot.
        self.tick.start()

    async def cog_unload(self):
        # Stop the loop cleanly when the cog is unloaded or the bot shuts down.
        self.tick.cancel()

    # The whole feature lives under one slash command group ("/reminder ...")
    # so subcommands stay namespaced. default_permissions hides the commands
    # from users without Manage Messages by default; server admins can override
    # the binding in Server Settings → Integrations.
    reminder_group = app_commands.Group(
        name="reminder",
        description="Manage scheduled weekly reminders.",
        default_permissions=discord.Permissions(manage_messages=True),
    )

    @reminder_group.command(name="add", description="Schedule a recurring weekly reminder.")
    @app_commands.describe(
        channel="Channel where the reminder will post",
        weekday="Day of the week",
        time="Time of day in 24h format, e.g. 18:00",
        lead_minutes="Minutes between firing and the event the timestamp points to",
        message="Message body (a relative timestamp is appended automatically)",
    )
    @app_commands.choices(weekday=WEEKDAY_CHOICES)
    async def add(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        weekday: app_commands.Choice[int],
        time: str,
        lead_minutes: app_commands.Range[int, 0, 10080],  # 0 minutes .. 1 week
        message: str,
    ):
        """Validate input, append a new reminder, persist, and confirm to the user."""
        try:
            t = datetime.strptime(time.strip(), "%H:%M").time()
        except ValueError:
            await interaction.response.send_message(
                f"Could not parse `{time}` — expected HH:MM (24-hour).", ephemeral=True
            )
            return
        # Monotonically increasing id so /remove can target a specific reminder.
        rid = self.data["next_id"]
        self.data["next_id"] += 1
        self.data["reminders"].append({
            "id": rid,
            "channel_id": channel.id,
            "weekday": weekday.value,
            "hour": t.hour,
            "minute": t.minute,
            "lead_minutes": lead_minutes,
            "message": message,
            # ISO date of the most recent fire; "" means never fired.
            "last_fired": "",
        })
        _save_data(self.data)
        await interaction.response.send_message(
            f"Added reminder `#{rid}`: every {weekday.name} at {t.strftime('%H:%M')} in {channel.mention}.",
            ephemeral=True,
        )

    @reminder_group.command(name="list", description="List all scheduled reminders.")
    async def list_(self, interaction: discord.Interaction):
        """Reply with a one-line summary of every reminder. Method name is `list_` to avoid shadowing the builtin."""
        if not self.data["reminders"]:
            await interaction.response.send_message("No reminders set.", ephemeral=True)
            return
        body = "\n".join(_format_reminder(r) for r in self.data["reminders"])
        await interaction.response.send_message(body, ephemeral=True)

    @reminder_group.command(name="test", description="Fire a reminder immediately for testing (does not affect its schedule).")
    @app_commands.describe(id="The reminder id from /reminder list")
    async def test(self, interaction: discord.Interaction, id: app_commands.Range[int, 1]):
        """Send the same content the scheduler would, without touching `last_fired`."""
        reminder = next((r for r in self.data["reminders"] if r["id"] == id), None)
        if reminder is None:
            await interaction.response.send_message(f"No reminder with id `{id}`.", ephemeral=True)
            return
        channel = self.client.get_channel(reminder["channel_id"])
        if channel is None:
            await interaction.response.send_message(
                f"Reminder `#{id}`'s channel (`{reminder['channel_id']}`) is not accessible.", ephemeral=True
            )
            return
        # Recompute the event timestamp from "now" so the rendered "in N hours"
        # is accurate for the test fire, not the originally scheduled time.
        event_time = datetime.now() + timedelta(minutes=reminder["lead_minutes"])
        content = f"{reminder['message']} <t:{int(event_time.timestamp())}:R>"
        try:
            await channel.send(content)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to send: {e}", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Test-fired reminder `#{id}` in {channel.mention}.", ephemeral=True
        )

    @reminder_group.command(name="remove", description="Remove a reminder by id.")
    @app_commands.describe(id="The reminder id from /reminder list")
    async def remove(self, interaction: discord.Interaction, id: app_commands.Range[int, 1]):
        """Drop the reminder with the given id and persist."""
        before = len(self.data["reminders"])
        self.data["reminders"] = [r for r in self.data["reminders"] if r["id"] != id]
        if len(self.data["reminders"]) == before:
            await interaction.response.send_message(f"No reminder with id `{id}`.", ephemeral=True)
            return
        _save_data(self.data)
        await interaction.response.send_message(f"Removed reminder `#{id}`.", ephemeral=True)

    @tasks.loop(seconds=30)
    async def tick(self):
        """
        Background poll that fires due reminders.

        Runs every 30 seconds. A reminder fires when the current weekday and
        HH:MM match its schedule and it hasn't already fired today (the
        `last_fired` ISO date guards against double-fire on the same minute).
        Failures to send a single reminder don't stop the loop or the other
        reminders from firing.
        """
        now = datetime.now()
        today_iso = now.date().isoformat()
        changed = False
        for r in self.data["reminders"]:
            if r["weekday"] != now.weekday():
                continue
            if r["hour"] != now.hour or r["minute"] != now.minute:
                continue
            if r.get("last_fired") == today_iso:
                continue
            channel = self.client.get_channel(r["channel_id"])
            if channel is None:
                # Channel was deleted or the bot can't see it — skip silently.
                continue
            event_time = now + timedelta(minutes=r["lead_minutes"])
            content = f"{r['message']} <t:{int(event_time.timestamp())}:R>"
            try:
                await channel.send(content)
                # Only mark fired on success so transient send failures get retried next tick.
                r["last_fired"] = today_iso
                changed = True
            except Exception:
                pass
        if changed:
            _save_data(self.data)

    @tick.before_loop
    async def before_tick(self):
        # Don't start ticking until the gateway is connected and caches are
        # populated; otherwise get_channel() would return None for everything.
        await self.client.wait_until_ready()


async def setup(client):
    # discord.py extension entry point — called by `bot.load_extension`.
    await client.add_cog(Reminders(client))
