import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timedelta

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WEEKDAY_CHOICES = [app_commands.Choice(name=n, value=i) for i, n in enumerate(WEEKDAY_NAMES)]

DATA_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "Reminders.json")


def _load_data():
    if not os.path.exists(DATA_PATH):
        return {"reminders": [], "next_id": 1}
    with open(DATA_PATH) as f:
        return json.load(f)


def _save_data(data):
    with open(DATA_PATH, "w") as f:
        json.dump(data, f, indent=2)


def _format_reminder(r):
    return (
        f"`#{r['id']}` <#{r['channel_id']}> — "
        f"{WEEKDAY_NAMES[r['weekday']]} {r['hour']:02d}:{r['minute']:02d} "
        f"(lead {r['lead_minutes']}m): {r['message']!r}"
    )


class Reminders(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.data = _load_data()

    async def cog_load(self):
        self.tick.start()

    async def cog_unload(self):
        self.tick.cancel()

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
        lead_minutes: app_commands.Range[int, 0, 10080],
        message: str,
    ):
        try:
            t = datetime.strptime(time.strip(), "%H:%M").time()
        except ValueError:
            await interaction.response.send_message(
                f"Could not parse `{time}` — expected HH:MM (24-hour).", ephemeral=True
            )
            return
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
            "last_fired": "",
        })
        _save_data(self.data)
        await interaction.response.send_message(
            f"Added reminder `#{rid}`: every {weekday.name} at {t.strftime('%H:%M')} in {channel.mention}.",
            ephemeral=True,
        )

    @reminder_group.command(name="list", description="List all scheduled reminders.")
    async def list_(self, interaction: discord.Interaction):
        if not self.data["reminders"]:
            await interaction.response.send_message("No reminders set.", ephemeral=True)
            return
        body = "\n".join(_format_reminder(r) for r in self.data["reminders"])
        await interaction.response.send_message(body, ephemeral=True)

    @reminder_group.command(name="test", description="Fire a reminder immediately for testing (does not affect its schedule).")
    @app_commands.describe(id="The reminder id from /reminder list")
    async def test(self, interaction: discord.Interaction, id: app_commands.Range[int, 1]):
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
        before = len(self.data["reminders"])
        self.data["reminders"] = [r for r in self.data["reminders"] if r["id"] != id]
        if len(self.data["reminders"]) == before:
            await interaction.response.send_message(f"No reminder with id `{id}`.", ephemeral=True)
            return
        _save_data(self.data)
        await interaction.response.send_message(f"Removed reminder `#{id}`.", ephemeral=True)

    @tasks.loop(seconds=30)
    async def tick(self):
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
                continue
            event_time = now + timedelta(minutes=r["lead_minutes"])
            content = f"{r['message']} <t:{int(event_time.timestamp())}:R>"
            try:
                await channel.send(content)
                r["last_fired"] = today_iso
                changed = True
            except Exception:
                pass
        if changed:
            _save_data(self.data)

    @tick.before_loop
    async def before_tick(self):
        await self.client.wait_until_ready()


async def setup(client):
    await client.add_cog(Reminders(client))
