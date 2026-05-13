"""
Recurring weekly reminders cog.

Exposes a `/reminder` slash command group with five subcommands:
  add       — schedule a recurring reminder (channel, weekday, HH:MM, lead, msg)
  list      — list all reminders (ephemeral)
  test      — fire a reminder immediately without affecting its schedule
  remove    — delete a reminder by id
  timezone  — change the IANA timezone all reminders are interpreted in

When fired the bot posts the message followed by a Discord relative
timestamp (`<t:UNIX:R>`) computed from `lead_minutes` after the fire time,
so a 120-minute lead renders as "in 2 hours" in the user's local timezone.

Schedules are interpreted in the timezone stored in
`data/Reminders.json` (defaults to **America/Los_Angeles**, i.e. PST/PDT).
DST behavior depends on the chosen zone — pick UTC if you want no DST;
a DST zone will skip a reminder scheduled inside the spring-forward gap
and rely on `last_fired` to prevent double-fire on the fall-back hour.

State is persisted in `data/Reminders.json` (gitignored, auto-created) so
reminders survive restarts. Writes are atomic (write-tmp + rename) and
load tolerates a corrupted file by quarantining it and starting fresh.
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

# Default timezone if the data file has no explicit one yet (fresh install
# or a pre-timezone-feature file). America/Los_Angeles automatically swings
# between PST and PDT, so users on the US Pacific coast get the right wall
# time year-round.
DEFAULT_TIMEZONE = "America/Los_Angeles"

# Python's datetime.weekday() returns 0=Monday..6=Sunday; index aligns with this list.
WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WEEKDAY_CHOICES = [app_commands.Choice(name=n, value=i) for i, n in enumerate(WEEKDAY_NAMES)]

# Persisted state lives at <repo>/data/Reminders.json — runtime state is kept
# out of src/ so source code and machine-generated files don't get mixed.
DATA_PATH = os.path.join(
    os.path.dirname(os.path.realpath(__file__)), "..", "..", "data", "Reminders.json"
)

# Discord caps a single message at 2000 chars. The fired content is the user's
# message followed by " <t:UNIX:R>" (~16 chars). Reserve some headroom so the
# combined post stays comfortably under the limit.
MAX_MESSAGE_LEN = 1900

# How many minutes back to search at startup for reminders that should have
# fired during the bot's downtime. Keeps the catch-up window tight so we don't
# spam old reminders if the bot was down for hours.
CATCHUP_WINDOW_MINUTES = 10

# Two AllowedMentions presets, picked per-reminder based on whether the
# *creator* had Mention Everyone permission in the target channel at /add
# time. The bot account itself can technically ping anyone — these presets
# stop reminder bodies from being weaponized into server-wide pings unless
# the original creator was already allowed to do that.
RESTRICTIVE_MENTIONS = discord.AllowedMentions(everyone=False, roles=False, users=True)
PRIVILEGED_MENTIONS = discord.AllowedMentions(everyone=True, roles=True, users=True)

# Detect mass-ping syntax in a message body so we can require the
# Mention Everyone permission before storing the reminder.
_EVERYONE_PATTERN = re.compile(r"@(everyone|here)\b")
_ROLE_MENTION_PATTERN = re.compile(r"<@&\d+>")


def _needs_mention_everyone(text: str) -> bool:
    """True if the message contains @everyone, @here, or a role mention."""
    return bool(_EVERYONE_PATTERN.search(text) or _ROLE_MENTION_PATTERN.search(text))


def _empty_state():
    return {"reminders": [], "next_id": 1, "timezone": DEFAULT_TIMEZONE}


def _load_data():
    """
    Read the persisted reminder list.

    Returns a fresh empty structure if the file is missing. If the file is
    present but corrupt, rename it aside (Reminders.json.bad-<timestamp>),
    log loudly, and return an empty structure so the bot can keep running.
    Backfills the `timezone` field on older files that pre-date it.
    """
    if not os.path.exists(DATA_PATH):
        return _empty_state()
    try:
        with open(DATA_PATH) as f:
            data = json.load(f)
    except json.JSONDecodeError:
        bad_path = f"{DATA_PATH}.bad-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        try:
            os.replace(DATA_PATH, bad_path)
            logger.error(
                "Corrupted Reminders.json quarantined to %s; starting with empty state", bad_path
            )
        except OSError:
            logger.exception("Could not quarantine corrupted Reminders.json at %s", DATA_PATH)
        return _empty_state()
    # Migrate older files that didn't have a timezone field.
    data.setdefault("timezone", DEFAULT_TIMEZONE)
    return data


def _save_data(data):
    """
    Persist the reminder list to disk atomically.

    Writes to <DATA_PATH>.tmp first, then os.replace's it over the real
    file. os.replace is atomic on POSIX and Windows, so a crash mid-write
    can never leave a half-written JSON file behind.
    """
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    tmp_path = DATA_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, DATA_PATH)


def _format_reminder(r, tz_name):
    """One-line summary of a reminder used by /reminder list."""
    return (
        f"`#{r['id']}` <#{r['channel_id']}> — "
        f"{WEEKDAY_NAMES[r['weekday']]} {r['hour']:02d}:{r['minute']:02d} {tz_name} "
        f"(lead {r['lead_minutes']}m): {r['message']!r}"
    )


def _preview(text, limit=120):
    """Compress text to a single line and truncate it for a confirmation reply."""
    flat = text.replace("\n", " ").strip()
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _summarize_reminder(r, tz_name):
    """Multi-line confirmation block describing what a reminder does."""
    return (
        f"every **{WEEKDAY_NAMES[r['weekday']]}** at "
        f"**{r['hour']:02d}:{r['minute']:02d} {tz_name}** "
        f"in <#{r['channel_id']}> (lead {r['lead_minutes']}m)\n"
        f"> {_preview(r['message'])}"
    )


def _build_content(reminder, fire_time):
    """Compose the message body the bot posts when a reminder fires."""
    event_time = fire_time + timedelta(minutes=reminder["lead_minutes"])
    return f"{reminder['message']} <t:{int(event_time.timestamp())}:R>"


class Reminders(commands.Cog):
    """Cog that registers the /reminder command group and runs the periodic fire loop."""

    def __init__(self, client):
        self.client = client
        # Load persisted reminders into memory at construction. All reads/writes
        # happen against this dict; the disk file is only touched on save.
        self.data = _load_data()

    def _tz(self):
        """ZoneInfo for the currently configured timezone, falling back to UTC if invalid."""
        name = self.data.get("timezone", DEFAULT_TIMEZONE)
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError:
            logger.error("Configured timezone %r is invalid; falling back to UTC", name)
            return ZoneInfo("UTC")

    async def cog_load(self):
        # discord.py 2.x lifecycle hook — start the background loop after the
        # cog has been fully attached to the bot.
        self.tick.start()

    async def cog_unload(self):
        # Stop the loop cleanly when the cog is unloaded or the bot shuts down.
        self.tick.cancel()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """
        Hard-gate every slash command in this cog on Manage Messages.

        The group's default_permissions is only a Discord-side hint that
        admins can override in Server Settings → Integrations. This check
        is the actual server-side enforcement: if the invoker lacks the
        permission, reply ephemerally and block the command from running.
        Note: applies to every app command in this cog, not just /reminder.
        """
        if interaction.permissions.manage_messages:
            return True
        await interaction.response.send_message(
            "You need the **Manage Messages** permission to use `/reminder` commands.",
            ephemeral=True,
        )
        return False

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
        weekday="Day of the week (in the configured timezone — see /reminder timezone)",
        time="Time of day in 24h, e.g. 18:00 (in the configured timezone)",
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
        # 1) Time format check.
        try:
            t = datetime.strptime(time.strip(), "%H:%M").time()
        except ValueError:
            await interaction.response.send_message(
                f"Could not parse `{time}` — expected HH:MM (24-hour).", ephemeral=True
            )
            return

        # 2) Reject messages that would bust Discord's 2000-char post limit
        # once the relative-timestamp suffix is appended.
        if len(message) > MAX_MESSAGE_LEN:
            await interaction.response.send_message(
                f"Message is too long ({len(message)} chars). Max {MAX_MESSAGE_LEN} so the "
                f"timestamp suffix still fits inside Discord's 2000-char limit.",
                ephemeral=True,
            )
            return

        # 3) Confirm the *invoking user* can post in the target channel. Without
        # this, anyone with Manage Messages anywhere in the guild could schedule
        # reminders into private channels they shouldn't otherwise reach.
        member = interaction.user
        perms = channel.permissions_for(member) if hasattr(channel, "permissions_for") else None
        if perms is None or not perms.send_messages:
            await interaction.response.send_message(
                f"You don't have permission to send messages in {channel.mention}.", ephemeral=True
            )
            return

        # 4) If the message uses @everyone / @here / role mentions, require
        # the creator to actually have Mention Everyone permission in the
        # target channel. Otherwise the bot account would let them bypass
        # their own permissions at fire time.
        allow_everyone_mentions = False
        if _needs_mention_everyone(message):
            if not perms.mention_everyone:
                await interaction.response.send_message(
                    "Your message contains `@everyone`, `@here`, or a role mention but you "
                    f"don't have **Mention Everyone** permission in {channel.mention}.",
                    ephemeral=True,
                )
                return
            allow_everyone_mentions = True

        # 5) Allocate id and persist.
        rid = self.data["next_id"]
        self.data["next_id"] += 1
        new_reminder = {
            "id": rid,
            "channel_id": channel.id,
            "weekday": weekday.value,
            "hour": t.hour,
            "minute": t.minute,
            "lead_minutes": lead_minutes,
            "message": message,
            # ISO date of the most recent fire; "" means never fired.
            "last_fired": "",
            # Whether @everyone / @here / role mentions in this reminder
            # should actually ping at fire time. Locked in at creation
            # based on the creator's permissions; doesn't update if their
            # permissions change later.
            "allow_everyone_mentions": allow_everyone_mentions,
        }
        self.data["reminders"].append(new_reminder)
        _save_data(self.data)
        tz_name = self.data.get("timezone", DEFAULT_TIMEZONE)
        await interaction.response.send_message(
            f"Added reminder `#{rid}` — {_summarize_reminder(new_reminder, tz_name)}",
            ephemeral=True,
        )

    @reminder_group.command(name="list", description="List all scheduled reminders.")
    async def list_(self, interaction: discord.Interaction):
        """
        Reply with a one-line summary of every reminder. Method name is `list_` to avoid
        shadowing the builtin.
        """
        if not self.data["reminders"]:
            await interaction.response.send_message("No reminders set.", ephemeral=True)
            return
        tz_name = self.data.get("timezone", DEFAULT_TIMEZONE)
        body = "\n".join(_format_reminder(r, tz_name) for r in self.data["reminders"])
        await interaction.response.send_message(body, ephemeral=True)

    @reminder_group.command(
        name="test",
        description="Fire a reminder immediately for testing (does not affect its schedule).",
    )
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
                f"Reminder `#{id}`'s channel (`{reminder['channel_id']}`) is not accessible.",
                ephemeral=True,
            )
            return
        # Recompute the event timestamp from "now" so the rendered "in N hours"
        # is accurate for the test fire, not the originally scheduled time.
        # `_build_content` only needs an absolute moment, so any tz works — UTC
        # keeps it explicit and matches what `tick` uses.
        content = _build_content(reminder, datetime.now(timezone.utc))
        allowed = (
            PRIVILEGED_MENTIONS if reminder.get("allow_everyone_mentions") else RESTRICTIVE_MENTIONS
        )
        try:
            await channel.send(content, allowed_mentions=allowed)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to send: {e}", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Test-fired reminder `#{id}` in {channel.mention}.\n> {_preview(reminder['message'])}",
            ephemeral=True,
        )

    @reminder_group.command(name="remove", description="Remove a reminder by id.")
    @app_commands.describe(id="The reminder id from /reminder list")
    async def remove(self, interaction: discord.Interaction, id: app_commands.Range[int, 1]):
        """Drop the reminder with the given id and persist."""
        # Snapshot the doomed reminder before filtering so the confirmation
        # can describe what the user just removed.
        target = next((r for r in self.data["reminders"] if r["id"] == id), None)
        if target is None:
            await interaction.response.send_message(f"No reminder with id `{id}`.", ephemeral=True)
            return
        self.data["reminders"] = [r for r in self.data["reminders"] if r["id"] != id]
        _save_data(self.data)
        tz_name = self.data.get("timezone", DEFAULT_TIMEZONE)
        await interaction.response.send_message(
            f"Removed reminder `#{id}` — {_summarize_reminder(target, tz_name)}",
            ephemeral=True,
        )

    @reminder_group.command(
        name="timezone",
        description="Change the IANA timezone all reminders are interpreted in.",
    )
    @app_commands.describe(tz="IANA name, e.g. UTC, America/Los_Angeles, Europe/Berlin, Asia/Tokyo")
    async def timezone_(self, interaction: discord.Interaction, tz: str):
        """
        Change the cog-wide timezone. Existing reminders' (weekday, HH:MM)
        stays as-stored — they're now interpreted in the new timezone, which
        means their wall-clock fire time effectively shifts. Surface that
        explicitly so the user isn't surprised.
        """
        try:
            ZoneInfo(tz)
        except ZoneInfoNotFoundError:
            await interaction.response.send_message(
                f"`{tz}` is not a valid IANA timezone name. Examples: `UTC`, "
                f"`America/Los_Angeles`, `Europe/Berlin`, `Asia/Tokyo`.",
                ephemeral=True,
            )
            return
        old = self.data.get("timezone", DEFAULT_TIMEZONE)
        self.data["timezone"] = tz
        _save_data(self.data)
        if old == tz:
            await interaction.response.send_message(
                f"Timezone is already `{tz}`. No change.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"Timezone changed from `{old}` to `{tz}`.\n"
            f"**Existing reminders' wall-clock times are now interpreted in `{tz}`** — "
            f"review with `/reminder list`.",
            ephemeral=True,
        )

    async def _fire(self, reminder, now):
        """Send a due reminder. Returns True if last_fired should be marked."""
        channel = self.client.get_channel(reminder["channel_id"])
        if channel is None:
            # Channel was deleted or the bot can't see it — skip silently.
            return False
        allowed = (
            PRIVILEGED_MENTIONS if reminder.get("allow_everyone_mentions") else RESTRICTIVE_MENTIONS
        )
        try:
            await channel.send(_build_content(reminder, now), allowed_mentions=allowed)
            return True
        except Exception:
            # Log the traceback; one bad reminder shouldn't kill the loop.
            logger.exception(
                "Failed to fire reminder #%s in channel %s",
                reminder["id"], reminder["channel_id"],
            )
            return False

    @tasks.loop(seconds=30)
    async def tick(self):
        """
        Background poll that fires due reminders.

        Runs every 30 seconds. A reminder fires when the current weekday
        and HH:MM in the configured timezone match its schedule and it
        hasn't already fired today (the `last_fired` ISO date guards
        against double-fire on the same minute). Failures to send a single
        reminder don't stop the loop or the other reminders from firing.
        """
        now = datetime.now(self._tz())
        today_iso = now.date().isoformat()
        changed = False
        # Snapshot the list so concurrent /reminder add or /remove during one
        # of the awaits below can't desync iteration or skip/duplicate entries.
        for r in list(self.data["reminders"]):
            if r["weekday"] != now.weekday():
                continue
            if r["hour"] != now.hour or r["minute"] != now.minute:
                continue
            if r.get("last_fired") == today_iso:
                continue
            if await self._fire(r, now):
                # Only mark fired on success so transient failures retry next tick.
                r["last_fired"] = today_iso
                changed = True
        if changed:
            _save_data(self.data)

    @tick.before_loop
    async def before_tick(self):
        # Don't start ticking until the gateway is connected and caches are
        # populated; otherwise get_channel() would return None for everything.
        await self.client.wait_until_ready()
        # Catch up on any reminders that should have fired during the bot's
        # downtime, so a brief restart across a scheduled minute doesn't
        # silently drop the reminder.
        await self._catch_up_missed()

    async def _catch_up_missed(self):
        """
        Fire any reminder whose scheduled minute fell within the past
        CATCHUP_WINDOW_MINUTES and hasn't already been marked fired today.
        Bounded window keeps a multi-hour outage from spamming old reminders.
        """
        now = datetime.now(self._tz())
        today_iso = now.date().isoformat()
        changed = False
        for r in list(self.data["reminders"]):
            if r["weekday"] != now.weekday():
                continue
            if r.get("last_fired") == today_iso:
                continue
            scheduled = now.replace(hour=r["hour"], minute=r["minute"], second=0, microsecond=0)
            delta_min = (now - scheduled).total_seconds() / 60
            if 0 < delta_min <= CATCHUP_WINDOW_MINUTES:
                logger.info("Catch-up firing reminder #%s (%.1f min late)", r["id"], delta_min)
                if await self._fire(r, now):
                    r["last_fired"] = today_iso
                    changed = True
        if changed:
            _save_data(self.data)


async def setup(client):
    # discord.py extension entry point — called by `bot.load_extension`.
    await client.add_cog(Reminders(client))
