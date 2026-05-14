<img align="right" src="assets/PetMe.png" width="150" alt="PekkaBot2 avatar">

<h1 align="center">⋆.ೃ࿔🌸*:･ $\color{#fda2f5}{\textbf{PekkaBot2}}$ *🌸࿔.ೃ⋆</h1>

<h4 align="center">🌸 A Personal Discord Bot 🌸</h4>

## 🎀 $\color{#fda2f5}{\textbf{Layout}}$

```
PekkaBot2/
├── Connection.py        # entry point — run this
├── src/
│   └── cogs/            # feature modules (auto-loaded on startup)
├── config/              # token, deps, docs
└── data/                # runtime state (gitignored)
```

## 🎀 $\color{#fda2f5}{\textbf{Tech Stack}}$

| Dependency | Version | Purpose |
|---|---|---|
| [discord.py](https://github.com/Rapptz/discord.py) | 2.7+ | Discord API wrapper |
| Python | 3.11+ | Runtime |

The entry point is [`Connection.py`](Connection.py) at the repo root; library code lives under [`src/`](src/).

## 🎀 $\color{#fda2f5}{\textbf{Setup}}$

### **1. Install dependencies**

```bash
pip install -r config/requirements.txt
```

### **2. BotConstants.py**

`config/BotConstants.py` is gitignored. Create it locally with at minimum:

```python
TOKEN = "YOUR_BOT_TOKEN"
INVITE_URL = "YOUR_INVITE_URL"


def get_token():
    return TOKEN


def get_invite_url():
    return INVITE_URL
```

`TOKEN` is your bot's secret. Copy it from your application's *Bot → Token* tab. Never commit it.

`INVITE_URL` is what `/invite` posts. Generate it from your application's *OAuth2 → URL Generator* tab.

### **3. Discord Developer Portal**

In the [Discord Developer Portal](https://discord.com/developers/applications), under **Bot → Privileged Gateway Intents**:
- **Message Content Intent** — leave **off** for the current slash-only setup. Only enable it later if you add prefix commands that need to read message text.

### **4. Run**

From the repo root:

```bash
python Connection.py
```

The bot logs to `output.log` in the launch directory.

## 🎀 $\color{#fda2f5}{\textbf{Architecture}}$

| Module | Description |
|---|---|
| [Connection.py](Connection.py) | Bot entry point at the repo root. |
| [config/BotConstants.py](config/BotConstants.py) | Holds the Discord token and exposes `get_token()` / `get_invite_url()`. |
| [src/cogs/Reminders.py](src/cogs/Reminders.py) | `/reminder` slash command group for recurring weekly reminders. |
| [src/cogs/Invite.py](src/cogs/Invite.py) | `/invite` slash command that returns the bot's OAuth2 invite link. |
| [data/](data/) | Auto-created at runtime. Holds `Reminders.json` (reminder schedules) and `UserTimezones.json` (per-user default timezones). |

## 🎀 $\color{#fda2f5}{\textbf{Adding a new cog}}$

Every `.py` file under `src/cogs/` is auto-loaded on startup by [`Connection`](Connection.py). To add a new feature, drop a file in that directory with this skeleton:

```python
import discord
from discord import app_commands
from discord.ext import commands


class MyCog(commands.Cog):
    def __init__(self, client):
        self.client = client

    @app_commands.command(name="hello", description="Say hi.")
    async def hello(self, interaction: discord.Interaction):
        await interaction.response.send_message("Hi!", ephemeral=True)


async def setup(client):
    await client.add_cog(MyCog(client))
```

Restart the bot and the new commands appear after the next slash-command sync. Discord can take up to an hour to globally propagate brand-new slash commands the first time.

## 🎀 $\color{#fda2f5}{\textbf{Commands}}$

### **Reminders (Manage Messages Permission)**

Five subcommands of the `/reminder` slash group. Permissions can be re-bound in *Server Settings → Integrations → [Your Bot] → reminder*.

| Command | Description |
|---|---|
| `/reminder add [channel] [weekdays] [time] [lead_minutes] [message]` | Schedule a recurring weekly reminder. `weekdays` is a single day, comma-separated list (`Mon, Wed, Fri`), or preset (`everyday` / `weekdays` / `weekends`). `time` is `HH:MM` 24-hour, interpreted in your stored timezone (see `/reminder timezone`, default `America/Los_Angeles`); the timezone is snapshotted onto the reminder at creation. `lead_minutes` controls the relative timestamp appended to the message (e.g. 120 → "in 2 hours"). Rejects sending to channels where the invoking user can't post; messages containing `@everyone`/`@here`/role mentions require the user to have **Mention Everyone** permission in the target channel. |
| `/reminder list` | Ephemeral list of every reminder with its `#id`. |
| `/reminder test [id]` | Fires a reminder immediately for verification. Does not affect its schedule. |
| `/reminder remove [id]` | Deletes a reminder. |
| `/reminder timezone [tz]` | Set **your** default timezone, used by future `/reminder add` calls you make. Accepts shorthand (`PST`, `EST`, `JST`, `UTC`, ...) or a full IANA name (`America/Los_Angeles`, `Europe/Berlin`). Stored per-user in `data/UserTimezones.json`. Existing reminders are unchanged — each one keeps the timezone snapshotted when it was created. |

**Sample output**

When a reminder fires, the bot posts:

```
Event starts <t:UNIX:R>
```

where `UNIX` is the event's Unix timestamp. Discord renders that token in each viewer's local timezone as a relative phrase:

> Event starts **in 2 hours**

### **Invite**

| Command | Description |
|---|---|
| `/invite` | Posts the bot's OAuth2 invite link so anyone can add it to another server. The link itself lives in `INVITE_URL` inside [config/BotConstants.py](config/BotConstants.py). |

## 🎀 $\color{#fda2f5}{\textbf{Authors}}$

- **@Pekkapost** — Bot Creator

Forked from the original [Narmaya Bot](https://github.com/Pekkapost/Narmaya-Bot) framework.
