# **PekkaBot2**

<p align="center"><em>🌸 A Personal Discord Bot 🌸</em></p>

## 🌸 $\color{#fda2f5}{\textbf{Layout}}$

```
PekkaBot2/
├── Connection.py        # entry point — run this
├── src/
│   └── cogs/            # feature modules (auto-loaded on startup)
├── config/              # token, deps, docs
└── data/                # runtime state (gitignored)
```

## 🌸 $\color{#fda2f5}{\textbf{Tech Stack}}$

| Dependency | Version | Purpose |
|---|---|---|
| [discord.py](https://github.com/Rapptz/discord.py) | 2.7+ | Discord API wrapper |
| Python | 3.11+ | Runtime |

The entry point is [`Connection.py`](Connection.py) at the repo root; library code lives under [`src/`](src/).

## 🌸 $\color{#fda2f5}{\textbf{Setup}}$

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

## 🌸 $\color{#fda2f5}{\textbf{Architecture}}$

| Module | Description |
|---|---|
| [Connection.py](Connection.py) | Bot entry point at the repo root. Inserts `src/` and `config/` onto sys.path, builds the client, syncs the slash-command tree, and auto-loads every cog under `src/cogs/`. |
| [config/BotConstants.py](config/BotConstants.py)&nbsp;<abbr title="local only — gitignored and auto-created">🔒</abbr> | Holds the Discord token and exposes `get_token()` / `get_invite_url()`. |
| [src/cogs/Reminders.py](src/cogs/Reminders.py) | `/reminder` slash command group for recurring weekly reminders, with persistence in `data/Reminders.json`&nbsp;<abbr title="local only — gitignored and auto-created">🔒</abbr>. |
| [src/cogs/Invite.py](src/cogs/Invite.py) | `/invite` slash command that returns the bot's OAuth2 invite link. |
| [data/](data/)&nbsp;<abbr title="local only — gitignored and auto-created">🔒</abbr> | Runtime state (currently `Reminders.json`). Auto-created on first write. |

<sub>🔒 = local only — gitignored and auto-created. Hover for tooltip.</sub>

## 🌸 $\color{#fda2f5}{\textbf{Adding a new cog}}$

Every `.py` file under `src/cogs/` is auto-loaded on startup by [`Connection.init_cogs`](Connection.py). To add a new feature, drop a file in that directory with this skeleton:

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

## 🌸 $\color{#fda2f5}{\textbf{Commands}}$

Slash commands are globally synced on startup (Discord can take up to an hour to propagate new commands the first time).

### **Reminders (Manage Messages permission)**

Four subcommands of the `/reminder` slash group. Permissions can be re-bound in *Server Settings → Integrations → PekkaBot2 → reminder*.

| Command | Description |
|---|---|
| `/reminder add channel weekday time lead_minutes message` | Schedule a recurring weekly reminder. `time` is `HH:MM` 24-hour, interpreted in the configured timezone (see `/reminder timezone`, default UTC). `lead_minutes` controls the relative timestamp appended to the message (e.g. 120 → "in 2 hours"). The bot strips `@everyone`/`@here`/role/user mentions from the message to prevent abuse, and rejects sending to channels where the invoking user can't post. |
| `/reminder list` | Ephemeral list of every reminder with its `#id`. |
| `/reminder test id` | Fires a reminder immediately for verification. Does not affect its schedule. |
| `/reminder remove id` | Deletes a reminder. |
| `/reminder timezone tz` | Change the IANA timezone all reminders are interpreted in (e.g. `UTC`, `America/Los_Angeles`, `Europe/Berlin`). Existing reminders' stored `weekday`/`HH:MM` are then read in the new timezone, which effectively shifts their wall-clock fire time. |

**Sample output**

When a reminder fires, the bot posts:

```
Event starts <t:UNIX:R>
```

…where `UNIX` is the event's Unix timestamp. Discord renders that token in each viewer's local timezone as a relative phrase:

> Event starts **in 2 hours**

### **Invite**

| Command | Description |
|---|---|
| `/invite` | Posts the bot's OAuth2 invite link so anyone can add it to another server. The link itself lives in `INVITE_URL` inside [config/BotConstants.py](config/BotConstants.py). |

## 🌸 $\color{#fda2f5}{\textbf{Authors}}$

- **@Pekkapost** — Bot Creator

Forked from the original [Narmaya Bot](https://github.com/Pekkapost/Narmaya-Bot) framework.
