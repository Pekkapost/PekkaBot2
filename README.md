# PekkaBot2

A personal Discord bot built around a recurring weekly reminder system. Users with the right permission can schedule reminders that auto-post on a chosen weekday and time, with a Discord relative timestamp embedded in the message.

Forked from the original Narmaya Bot framework and rewritten in Python.

## Tech Stack

| Dependency | Version | Purpose |
|---|---|---|
| [discord.py](https://github.com/Rapptz/discord.py) | 2.x | Discord API wrapper |
| Python | 3.11+ | Runtime |

The entry point is [`src/Connection.py`](src/Connection.py).

## Setup

### 1. BotConstants.py

`src/BotConstants.py` is gitignored. Create it locally with at minimum:

```python
TOKEN = "YOUR_BOT_TOKEN"


def getToken():
    return TOKEN
```

### 2. Discord Developer Portal

In the [Discord Developer Portal](https://discord.com/developers/applications), under **Bot → Privileged Gateway Intents**, enable:
- **Message Content Intent** — required if you ever add prefix commands; safe to leave on for slash-only use.

When inviting the bot to a server, include both the `bot` and `applications.commands` scopes so slash commands appear.

### 3. Reminders.json

Auto-created at `src/Reminders.json` the first time `/reminder add` runs. No manual setup needed.

### 4. Run

From the repo root:

```bash
cd src
python Connection.py
```

The bot logs to `output.log` next to the launch directory.

## Architecture

| Module | Description |
|---|---|
| [src/Connection.py](src/Connection.py) | Bot entry point. Builds the client, syncs the slash-command tree, and auto-loads every cog under `src/cogs/`. |
| [src/BotConstants.py](src/BotConstants.py) | Gitignored. Holds the Discord token and exposes `getToken()`. |
| [src/cogs/Reminders.py](src/cogs/Reminders.py) | `/reminder` slash command group for recurring weekly reminders, with persistence in `src/Reminders.json`. |

## Commands

Slash commands are globally synced on startup (Discord can take up to an hour to propagate new commands the first time).

### Reminders (Manage Messages permission)

All four are subcommands of the `/reminder` slash group. Permissions can be re-bound in *Server Settings → Integrations → PekkaBot2 → reminder*.

| Command | Description |
|---|---|
| `/reminder add channel weekday time lead_minutes message` | Schedule a recurring weekly reminder. `time` is `HH:MM` 24-hour in the bot host's local timezone. `lead_minutes` controls the relative timestamp appended to the message (e.g. 120 → "in 2 hours"). |
| `/reminder list` | Ephemeral list of every reminder with its `#id`. |
| `/reminder test id` | Fires a reminder immediately for verification. Does not affect its schedule. |
| `/reminder remove id` | Deletes a reminder. |

When a reminder fires, the posted message is `<your message> <t:UNIX:R>` so Discord renders the relative timestamp in each viewer's local timezone.

## Authors

- **@Pekkapost** — GBFR Narmaya Bot Creator
- **@Bae** — GBFR Narmaya Bot Contributor
