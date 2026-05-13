# **PekkaBot2**

<p align="center"><em>🌸 A Personal Discord Bot 🌸</em></p>

## 🌸 $\color{#fda2f5}{\textbf{Tech Stack}}$

| Dependency | Version | Purpose |
|---|---|---|
| [discord.py](https://github.com/Rapptz/discord.py) | 2.x | Discord API wrapper |
| Python | 3.11+ | Runtime |

The entry point is [`src/Connection.py`](src/Connection.py).

## 🌸 $\color{#fda2f5}{\textbf{Setup}}$

### **1. Install dependencies**

```bash
pip install -r requirements.txt
```

### **2. BotConstants.py**

`src/BotConstants.py` is gitignored. Create it locally with at minimum:

```python
TOKEN = "YOUR_BOT_TOKEN"


def getToken():
    return TOKEN
```

### **3. Discord Developer Portal**

In the [Discord Developer Portal](https://discord.com/developers/applications), under **Bot → Privileged Gateway Intents**, enable:
- **Message Content Intent** — required if you ever add prefix commands; safe to leave on for slash-only use.

### **4. Run**

From the repo root:

```bash
cd src
python Connection.py
```

The bot logs to `output.log` in the launch directory.

## 🌸 $\color{#fda2f5}{\textbf{Architecture}}$

| Module | Description |
|---|---|
| [src/Connection.py](src/Connection.py) | Bot entry point. Builds the client, syncs the slash-command tree, and auto-loads every cog under `src/cogs/`. |
| [src/BotConstants.py](src/BotConstants.py) <abbr title="local only — gitignored and auto-created">🔒</abbr> | Holds the Discord token and exposes `getToken()`. |
| [src/cogs/Reminders.py](src/cogs/Reminders.py) | `/reminder` slash command group for recurring weekly reminders, with persistence in `data/Reminders.json` <abbr title="local only — gitignored and auto-created">🔒</abbr>. |
| [src/cogs/Invite.py](src/cogs/Invite.py) | `/invite` slash command that returns the bot's OAuth2 invite link. |

<sub>🔒 = local only — gitignored and auto-created. Hover for tooltip.</sub>

## 🌸 $\color{#fda2f5}{\textbf{Adding a new cog}}$

Every `.py` file under `src/cogs/` is auto-loaded on startup by [`Connection.init_cogs`](src/Connection.py). To add a new feature, drop a file in that directory with this skeleton:

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
| `/reminder add channel weekday time lead_minutes message` | Schedule a recurring weekly reminder. `time` is `HH:MM` 24-hour in the bot host's local timezone. `lead_minutes` controls the relative timestamp appended to the message (e.g. 120 → "in 2 hours"). |
| `/reminder list` | Ephemeral list of every reminder with its `#id`. |
| `/reminder test id` | Fires a reminder immediately for verification. Does not affect its schedule. |
| `/reminder remove id` | Deletes a reminder. |

**Sample output**

When a reminder fires, the bot posts:

```
Event starts <t:1715620800:R>
```

…which Discord renders in each viewer's local timezone as:

> Event starts **in 2 hours**

### **Invite**

| Command | Description |
|---|---|
| `/invite` | Posts the bot's OAuth2 invite link so anyone can add it to another server. Edit `INVITE_URL` in [src/cogs/Invite.py](src/cogs/Invite.py) to change the link. |

## 🌸 $\color{#fda2f5}{\textbf{Authors}}$

- **@Pekkapost** — Bot Creator

Forked from the original [Narmaya Bot](https://github.com/Pekkapost/Narmaya-Bot) framework.
