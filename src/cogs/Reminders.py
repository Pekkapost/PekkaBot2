"""
Recurring weekly reminders cog.

Exposes a `/reminder` slash command group with five subcommands:
  add       — schedule a recurring reminder (channel, weekdays, HH:MM, lead, msg)
  remove    — delete a reminder by id
  list      — list all reminders (ephemeral)
  timezone  — set the invoking user's default timezone for new reminders
  test      — fire a reminder immediately without affecting its schedule

When fired the bot posts the message followed by a Discord relative
timestamp (`<t:UNIX:R>`) computed from `lead_minutes` after the fire time,
so a 120-minute lead renders as "in 2 hours" in the user's local timezone.

**Timezones are per-user.** Each user has a default IANA zone stored in
`data/UserTimezones.json` (set with `/reminder timezone`, default
**America/Los_Angeles**). At `/reminder add` the creator's default is
snapshotted onto the new reminder, and the scheduler evaluates each
reminder in that stored zone. Changing your default later only affects
*new* reminders — existing ones keep firing in their original zone.

State is persisted in `data/Reminders.json` and `data/UserTimezones.json`
(both gitignored and auto-created). Writes are atomic (write-tmp + rename)
and loads tolerate corrupted files by quarantining them and starting fresh.
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from typing import TypedDict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord import app_commands
from discord.ext import commands, tasks

logger = logging.getLogger(__name__)


class Reminder(TypedDict):
    """In-memory shape of one reminder record persisted in Reminders.json."""

    id: int
    channel_id: int
    weekdays: list[int]
    hour: int
    minute: int
    lead_minutes: int
    message: str
    timezone: str
    last_fired: str
    allow_everyone_mentions: bool


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default IANA zone if a user has never set their own. America/Los_Angeles
# auto-tracks PST/PDT.
DEFAULT_TIMEZONE = "America/Los_Angeles"

# Python's datetime.weekday() returns 0=Monday..6=Sunday; index aligns with this list.
WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Lookup table for parsing user-typed day names. Accepts both the full name and
# the 3-letter abbreviation, case-insensitive ("mon", "Monday", "MON" all work).
_WEEKDAY_LOOKUP: dict[str, int] = {}
for _i, _n in enumerate(WEEKDAY_NAMES):
    _WEEKDAY_LOOKUP[_n.lower()] = _i
    _WEEKDAY_LOOKUP[_n[:3].lower()] = _i
del _i, _n

# Convenience presets the user can type instead of listing days individually.
_WEEKDAY_PRESETS: dict[str, list[int]] = {
    "everyday": [0, 1, 2, 3, 4, 5, 6],
    "daily": [0, 1, 2, 3, 4, 5, 6],
    "weekdays": [0, 1, 2, 3, 4],
    "weekends": [5, 6],
}

# Runtime state lives at <repo>/data/, kept out of src/ so source code and
# machine-generated files don't get mixed.
_DATA_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "..", "data")
DATA_PATH = os.path.join(_DATA_DIR, "Reminders.json")
# Per-user default timezones: {"<discord_user_id_str>": "<IANA tz name>", ...}.
# Looked up at /reminder add; updated by /reminder timezone.
USER_TZ_PATH = os.path.join(_DATA_DIR, "UserTimezones.json")

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

# Common timezone abbreviations mapped to their canonical IANA zone. Same-zone
# DST/standard variants (PST/PDT, EST/EDT, ...) collapse to one IANA name —
# IANA zones already track DST automatically, so the abbreviation is just a
# user-friendly alias. Lookup is case-insensitive (see _resolve_timezone).
# IST is intentionally omitted because it's ambiguous (India / Israel / Ireland).
_TIMEZONE_ALIASES: dict[str, str] = {
    "PST": "America/Los_Angeles", "PDT": "America/Los_Angeles", "PT": "America/Los_Angeles",
    "MST": "America/Denver", "MDT": "America/Denver", "MT": "America/Denver",
    "CST": "America/Chicago", "CDT": "America/Chicago", "CT": "America/Chicago",
    "EST": "America/New_York", "EDT": "America/New_York", "ET": "America/New_York",
    "AKST": "America/Anchorage", "AKDT": "America/Anchorage",
    "HST": "Pacific/Honolulu",
    "UTC": "UTC", "GMT": "UTC",
    "BST": "Europe/London",
    "CET": "Europe/Berlin", "CEST": "Europe/Berlin",
    "JST": "Asia/Tokyo",
    "KST": "Asia/Seoul",
    "AEST": "Australia/Sydney", "AEDT": "Australia/Sydney",
    "NZST": "Pacific/Auckland", "NZDT": "Pacific/Auckland",
}


# ---------------------------------------------------------------------------
# Generic helpers (no module-state dependencies)
# ---------------------------------------------------------------------------

def _atomic_write_json(path: str, payload: object) -> None:
    """
    Atomic JSON writer used for both Reminders.json and UserTimezones.json.

    Writes to <path>.tmp first, then os.replace's it over the real file.
    os.replace is atomic on POSIX and Windows, so a crash mid-write can
    never leave a half-written JSON file behind.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp_path, path)


def _safe_zone(name: str) -> ZoneInfo:
    """ZoneInfo by name, falling back to UTC if the name is unknown to the host."""
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        logger.error("Timezone %r is invalid; falling back to UTC", name)
        return ZoneInfo("UTC")


def _resolve_timezone(name: str) -> str:
    """
    Resolve a user-typed timezone string to a canonical IANA zone name.

    Accepts common shorthand (PST, EST, JST, UTC, ...) case-insensitively or
    a full IANA name (America/Los_Angeles, Europe/Berlin). Raises ValueError
    with a helpful message on unknown input.
    """
    name = name.strip()
    if not name:
        raise ValueError("Timezone is empty.")
    canonical = _TIMEZONE_ALIASES.get(name.upper())
    if canonical:
        return canonical
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError:
        raise ValueError(
            f"`{name}` is not a recognized timezone. Try a shorthand like "
            f"`PST`, `EST`, `JST`, `UTC`, or a full IANA name like "
            f"`America/Los_Angeles`."
        )
    return name


def _parse_weekdays(spec: str) -> list[int]:
    """
    Parse a user-supplied weekday spec into a sorted list of unique 0..6 ints.

    Accepts a single preset (e.g. "weekdays"), a single day, or a comma-
    separated list of days/presets ("Mon, Wed, Fri" / "weekends, Mon").
    Raises ValueError with a helpful message on bad input.
    """
    if not spec:
        raise ValueError("Weekday spec is empty.")
    spec = spec.strip().lower()
    output: set[int] = set()
    for item in (i.strip() for i in spec.split(",")):
        if not item:
            continue
        if item in _WEEKDAY_PRESETS:
            output.update(_WEEKDAY_PRESETS[item])
        elif item in _WEEKDAY_LOOKUP:
            output.add(_WEEKDAY_LOOKUP[item])
        else:
            raise ValueError(
                f"Unknown weekday `{item}`. Use full names (Monday), 3-letter "
                f"abbreviations (Mon), or presets (everyday, weekdays, weekends)."
            )
    if not output:
        raise ValueError("No valid weekdays in spec.")
    return sorted(output)


def _format_weekdays(days: list[int]) -> str:
    """Render a list of weekday ints as a compact human string."""
    days = sorted(set(days))
    if days == [0, 1, 2, 3, 4, 5, 6]:
        return "Every day"
    if days == [0, 1, 2, 3, 4]:
        return "Weekdays"
    if days == [5, 6]:
        return "Weekends"
    if len(days) == 1:
        return WEEKDAY_NAMES[days[0]]
    return ", ".join(WEEKDAY_NAMES[d][:3] for d in days)


def _needs_mention_everyone(text: str) -> bool:
    """True if the message contains @everyone, @here, or a role mention."""
    return bool(_EVERYONE_PATTERN.search(text) or _ROLE_MENTION_PATTERN.search(text))


def _preview(text: str, limit: int = 120) -> str:
    """Compress text to a single line and truncate it for a confirmation reply."""
    flat = text.replace("\n", " ").strip()
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


# ---------------------------------------------------------------------------
# Persistence (Reminders.json + UserTimezones.json)
# ---------------------------------------------------------------------------

def _empty_state() -> dict:
    return {"reminders": [], "next_id": 1}


def _load_data() -> dict:
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
            logger.exception("Could not quarantine corrupted %s", DATA_PATH)
        return _empty_state()
    # The old format kept a single global "timezone" key; now timezones live
    # per-reminder (snapshotted from the creator's stored default at /add time)
    # and per-user (in UserTimezones.json). Use the legacy global as the
    # fallback when backfilling reminders that were created before that switch.
    legacy_tz = data.pop("timezone", DEFAULT_TIMEZONE)
    for reminder in data.get("reminders", []):
        # Migrate single-weekday reminders (pre-multi-day support) to a list.
        if "weekdays" not in reminder and "weekday" in reminder:
            reminder["weekdays"] = [reminder.pop("weekday")]
        # Backfill per-reminder timezone for entries created before per-user TZs.
        reminder.setdefault("timezone", legacy_tz)
    return data


def _save_data(data: dict) -> None:
    """Persist the reminder list to disk atomically."""
    _atomic_write_json(DATA_PATH, data)


def _load_user_tzs() -> dict:
    """
    Read the per-user timezone map. Missing file → empty dict. Corrupt
    file → quarantined and started fresh, same pattern as Reminders.json.
    """
    if not os.path.exists(USER_TZ_PATH):
        return {}
    try:
        with open(USER_TZ_PATH) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise json.JSONDecodeError("not an object", "", 0)
        return data
    except json.JSONDecodeError:
        bad_path = (
            f"{USER_TZ_PATH}.bad-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        )
        try:
            os.replace(USER_TZ_PATH, bad_path)
            logger.error(
                "Corrupted UserTimezones.json quarantined to %s; starting with empty state",
                bad_path,
            )
        except OSError:
            logger.exception("Could not quarantine corrupted %s", USER_TZ_PATH)
        return {}


def _save_user_tzs(mapping: dict) -> None:
    _atomic_write_json(USER_TZ_PATH, mapping)


def _get_user_tz(user_id: int | str) -> str:
    """Return the user's stored timezone, falling back to DEFAULT_TIMEZONE."""
    mapping = _load_user_tzs()
    return mapping.get(str(user_id), DEFAULT_TIMEZONE)


def _set_user_tz(user_id: int | str, tz: str) -> None:
    """Persist a user's timezone choice. Caller is responsible for validating tz."""
    mapping = _load_user_tzs()
    mapping[str(user_id)] = tz
    _save_user_tzs(mapping)


# ---------------------------------------------------------------------------
# Reminder display formatting
# ---------------------------------------------------------------------------

def _format_reminder(reminder: Reminder) -> str:
    """One-line summary of a reminder used by /reminder list."""
    tz_name = reminder.get("timezone", DEFAULT_TIMEZONE)
    return (
        f"`#{reminder['id']}` <#{reminder['channel_id']}> — "
        f"{_format_weekdays(reminder['weekdays'])} "
        f"{reminder['hour']:02d}:{reminder['minute']:02d} {tz_name} "
        f"(lead {reminder['lead_minutes']}m): {reminder['message']!r}"
    )


def _summarize_reminder(reminder: Reminder) -> str:
    """Multi-line confirmation block describing what a reminder does."""
    tz_name = reminder.get("timezone", DEFAULT_TIMEZONE)
    return (
        f"**{_format_weekdays(reminder['weekdays'])}** at "
        f"**{reminder['hour']:02d}:{reminder['minute']:02d} {tz_name}** "
        f"in <#{reminder['channel_id']}> (lead {reminder['lead_minutes']}m)\n"
        f"> {_preview(reminder['message'])}"
    )


def _build_content(reminder: Reminder, fire_time: datetime) -> str:
    """Compose the message body the bot posts when a reminder fires."""
    event_time = fire_time + timedelta(minutes=reminder["lead_minutes"])
    return f"{reminder['message']} <t:{int(event_time.timestamp())}:R>"


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------


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

    # -----------------------------------------------------------------------
    # Slash command group + subcommands
    # -----------------------------------------------------------------------

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
        weekdays=(
            "Day(s) of the week. Single day, comma-separated (e.g. 'Mon, Wed, Fri'), "
            "or preset (everyday, weekdays, weekends)."
        ),
        time="Time of day in 24h, e.g. 18:00 (in the configured timezone)",
        lead_minutes="Minutes between firing and the event the timestamp points to",
        message="Message body (a relative timestamp is appended automatically)",
    )
    async def add(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        weekdays: str,
        time: str,
        lead_minutes: app_commands.Range[int, 0, 10080],  # 0 minutes .. 1 week
        message: str,
    ) -> None:
        """Validate input, append a new reminder, persist, and confirm to the user."""
        # 1) Parse weekdays (single, list, or preset).
        try:
            day_list = _parse_weekdays(weekdays)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        # 2) Time format check.
        try:
            t = datetime.strptime(time.strip(), "%H:%M").time()
        except ValueError:
            await interaction.response.send_message(
                f"Could not parse `{time}` — expected HH:MM (24-hour).", ephemeral=True
            )
            return

        # 3) Reject messages that would bust Discord's 2000-char post limit
        # once the relative-timestamp suffix is appended.
        if len(message) > MAX_MESSAGE_LEN:
            await interaction.response.send_message(
                f"Message is too long ({len(message)} chars). Max {MAX_MESSAGE_LEN} so the "
                f"timestamp suffix still fits inside Discord's 2000-char limit.",
                ephemeral=True,
            )
            return

        # 4) Confirm the *invoking user* can post in the target channel. Without
        # this, anyone with Manage Messages anywhere in the guild could schedule
        # reminders into private channels they shouldn't otherwise reach.
        member = interaction.user
        perms = channel.permissions_for(member) if hasattr(channel, "permissions_for") else None
        if perms is None or not perms.send_messages:
            await interaction.response.send_message(
                f"You don't have permission to send messages in {channel.mention}.", ephemeral=True
            )
            return

        # 5) If the message uses @everyone / @here / role mentions, require
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

        # 6) Snapshot the creator's stored timezone onto the new reminder so
        # the schedule fires in their preferred wall-clock — even if they later
        # change their default. Falls back to DEFAULT_TIMEZONE if unset.
        user_tz = _get_user_tz(interaction.user.id)

        # 7) Allocate id and persist.
        rid = self.data["next_id"]
        self.data["next_id"] += 1
        new_reminder = {
            "id": rid,
            "channel_id": channel.id,
            "weekdays": day_list,
            "hour": t.hour,
            "minute": t.minute,
            "lead_minutes": lead_minutes,
            "message": message,
            # IANA timezone the schedule is interpreted in. Snapshotted from
            # the creator's stored default; never updates after creation.
            "timezone": user_tz,
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
        await interaction.response.send_message(
            f"Added reminder `#{rid}` — {_summarize_reminder(new_reminder)}",
            ephemeral=True,
        )

    @reminder_group.command(name="remove", description="Remove a reminder by id.")
    @app_commands.rename(reminder_id="id")
    @app_commands.describe(reminder_id="The reminder id from /reminder list")
    async def remove(
        self, interaction: discord.Interaction, reminder_id: app_commands.Range[int, 1]
    ) -> None:
        """Drop the reminder with the given id and persist."""
        # Snapshot the doomed reminder before filtering so the confirmation
        # can describe what the user just removed.
        target = next(
            (reminder for reminder in self.data["reminders"] if reminder["id"] == reminder_id),
            None,
        )
        if target is None:
            await interaction.response.send_message(
                f"No reminder with id `{reminder_id}`.", ephemeral=True
            )
            return
        self.data["reminders"] = [
            reminder for reminder in self.data["reminders"] if reminder["id"] != reminder_id
        ]
        _save_data(self.data)
        await interaction.response.send_message(
            f"Removed reminder `#{reminder_id}` — {_summarize_reminder(target)}",
            ephemeral=True,
        )

    @reminder_group.command(name="list", description="List all scheduled reminders.")
    async def list_(self, interaction: discord.Interaction) -> None:
        """
        Reply with a one-line summary of every reminder. Method name is `list_` to avoid
        shadowing the builtin.
        """
        if not self.data["reminders"]:
            await interaction.response.send_message("No reminders set.", ephemeral=True)
            return
        body = "\n".join(_format_reminder(reminder) for reminder in self.data["reminders"])
        await interaction.response.send_message(body, ephemeral=True)

    @reminder_group.command(
        name="timezone",
        description="Set your default timezone for new reminders you add.",
    )
    @app_commands.describe(
        tz="Shorthand (PST, EST, JST, UTC, ...) or IANA name (America/Los_Angeles, Europe/Berlin)."
    )
    async def timezone_(self, interaction: discord.Interaction, tz: str) -> None:
        """
        Set the *invoking user's* default timezone, persisted in
        UserTimezones.json. The next /reminder add by that user snapshots
        this value onto the new reminder. Existing reminders are unaffected;
        they keep whatever timezone they were created with.
        """
        try:
            canonical = _resolve_timezone(tz)
        except ValueError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        old = _get_user_tz(interaction.user.id)
        if old == canonical:
            await interaction.response.send_message(
                f"Your default timezone is already `{canonical}`.", ephemeral=True
            )
            return
        _set_user_tz(interaction.user.id, canonical)
        # If they typed an alias, surface the canonical zone so they know what
        # actually got stored (PST → America/Los_Angeles).
        typed = tz.strip()
        shown = (
            f"`{canonical}`" if typed == canonical
            else f"`{canonical}` (resolved from `{typed}`)"
        )
        await interaction.response.send_message(
            f"Your default timezone is now {shown} (was `{old}`). "
            "New reminders you add will use it; existing reminders are unchanged.",
            ephemeral=True,
        )

    @reminder_group.command(
        name="test",
        description="Fire a reminder immediately for testing (does not affect its schedule).",
    )
    @app_commands.rename(reminder_id="id")
    @app_commands.describe(reminder_id="The reminder id from /reminder list")
    async def test(
        self, interaction: discord.Interaction, reminder_id: app_commands.Range[int, 1]
    ) -> None:
        """Send the same content the scheduler would, without touching `last_fired`."""
        reminder = next(
            (reminder for reminder in self.data["reminders"] if reminder["id"] == reminder_id),
            None,
        )
        if reminder is None:
            await interaction.response.send_message(
                f"No reminder with id `{reminder_id}`.", ephemeral=True
            )
            return
        channel = self.client.get_channel(reminder["channel_id"])
        if channel is None:
            await interaction.response.send_message(
                f"Reminder `#{reminder_id}`'s channel "
                f"(`{reminder['channel_id']}`) is not accessible.",
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
            await interaction.response.send_message(f"Failed to send: {e}.", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Test-fired reminder `#{reminder_id}` in {channel.mention}.\n"
            f"> {_preview(reminder['message'])}",
            ephemeral=True,
        )

    # -----------------------------------------------------------------------
    # Background scheduler
    # -----------------------------------------------------------------------

    async def _fire(self, reminder: Reminder, fire_time: datetime) -> bool:
        """Send a due reminder. Returns True if last_fired should be marked."""
        channel = self.client.get_channel(reminder["channel_id"])
        if channel is None:
            # Channel was deleted or the bot can't see it — skip silently.
            return False
        allowed = (
            PRIVILEGED_MENTIONS if reminder.get("allow_everyone_mentions") else RESTRICTIVE_MENTIONS
        )
        try:
            await channel.send(_build_content(reminder, fire_time), allowed_mentions=allowed)
            return True
        except Exception:
            # Log the traceback; one bad reminder shouldn't kill the loop.
            logger.exception(
                "Failed to fire reminder #%s in channel %s",
                reminder["id"], reminder["channel_id"],
            )
            return False

    @tasks.loop(seconds=30)
    async def tick(self) -> None:
        """
        Background poll that fires due reminders.

        Runs every 30 seconds. Each reminder is evaluated in its own stored
        timezone (set at creation from the creator's default). A reminder
        fires when the local weekday and HH:MM in that timezone match its
        schedule and it hasn't already fired today (the `last_fired` ISO
        date guards against double-fire on the same minute). One bad
        reminder is logged but doesn't stop the others from firing.
        """
        changed = False
        # Snapshot the list so concurrent /reminder add or /remove during one
        # of the awaits below can't desync iteration or skip/duplicate entries.
        for reminder in list(self.data["reminders"]):
            fire_time = datetime.now(_safe_zone(reminder.get("timezone", DEFAULT_TIMEZONE)))
            today_iso = fire_time.date().isoformat()
            if fire_time.weekday() not in reminder["weekdays"]:
                continue
            if reminder["hour"] != fire_time.hour or reminder["minute"] != fire_time.minute:
                continue
            if reminder.get("last_fired") == today_iso:
                continue
            if await self._fire(reminder, fire_time):
                # Only mark fired on success so transient failures retry next tick.
                reminder["last_fired"] = today_iso
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

    async def _catch_up_missed(self) -> None:
        """
        Fire any reminder whose scheduled minute fell within the past
        CATCHUP_WINDOW_MINUTES and hasn't already been marked fired today.
        Each reminder is evaluated in its own stored timezone. Bounded window
        keeps a multi-hour outage from spamming old reminders.
        """
        changed = False
        for reminder in list(self.data["reminders"]):
            fire_time = datetime.now(_safe_zone(reminder.get("timezone", DEFAULT_TIMEZONE)))
            today_iso = fire_time.date().isoformat()
            if fire_time.weekday() not in reminder["weekdays"]:
                continue
            if reminder.get("last_fired") == today_iso:
                continue
            scheduled = fire_time.replace(
                hour=reminder["hour"], minute=reminder["minute"], second=0, microsecond=0
            )
            delta_min = (fire_time - scheduled).total_seconds() / 60
            if 0 < delta_min <= CATCHUP_WINDOW_MINUTES:
                logger.info(
                    "Catch-up firing reminder #%s (%.1f min late)", reminder["id"], delta_min
                )
                if await self._fire(reminder, fire_time):
                    reminder["last_fired"] = today_iso
                    changed = True
        if changed:
            _save_data(self.data)


async def setup(client):
    # discord.py extension entry point — called by `bot.load_extension`.
    await client.add_cog(Reminders(client))
