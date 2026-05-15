<div align="center">
<table>
<tr valign="top">
<td>

<h1 align="center">⋆.ೃ࿔🌸*:･ $\color{#fda2f5}{\textbf{PekkaBot2}}$ *🌸࿔.ೃ⋆</h1>

<h4 align="center">🌸 A Personal Discord Bot 🌸</h4>

</td>
<td width="170">
<img src="assets/PetMe.png" width="150" alt="PekkaBot2 avatar">
</td>
</tr>
</table>
</div>

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

Restart the bot and the new commands appear after the next slash-command sync. Discord can take up to an hour to globally propagate brand-new slash commands the first time. Files starting with `_` (e.g. `__init__.py`, `_helpers.py`) are skipped, so you can keep cog-internal support modules alongside the cogs.

## 🎀 $\color{#fda2f5}{\textbf{Commands}}$

### **Reminders (Manage Messages Permission)**

Five subcommands of the `/reminder` slash group. Permissions can be re-bound in *Server Settings → Integrations → [Your Bot] → reminder*.

| Command | Description |
|---|---|
| `/reminder add [channel] [weekdays] [time] [lead_minutes] [message]` | Schedule a recurring reminder. `weekdays` accepts a day, comma-separated list, or preset (`everyday`/`weekdays`/`weekends`). `time` is `HH:MM` 24-hour. `lead_minutes` is the lead time before the event the embedded timestamp points to. |
| `/reminder list` | Ephemeral list of every reminder with its `#id`. |
| `/reminder test [id]` | Fires a reminder immediately. Does not affect its schedule. |
| `/reminder remove [id]` | Deletes a reminder. |
| `/reminder timezone [tz]` | Set your default timezone for new `/reminder add` calls (shorthand like `PST` or a full IANA name). Existing reminders keep the timezone they were created with. |

Times use your stored timezone (default `America/Los_Angeles`). `/add` rejects channels you can't post in, and rejects `@everyone`/`@here`/`@role` mentions unless you have **Mention Everyone** there.

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

## 🎀 $\color{#fda2f5}{\textbf{Limitations}}$

- Slash-command updates take up to ~1 hour to globally propagate the first time. Set `SYNC_GUILD_ID` in [`Connection.py`](Connection.py) to your home guild's id for instant per-guild syncs while iterating.
- The scheduler matches reminders at minute granularity; if the bot is offline through a scheduled minute, a startup catch-up pass will fire any reminder that was due in the last 10 minutes (`CATCHUP_WINDOW_MINUTES`). Outages longer than that drop the missed fire.
- DST behavior depends on the chosen timezone. UTC has no DST. A DST zone (e.g. `America/Los_Angeles`) will skip a reminder scheduled inside the spring-forward gap and rely on `last_fired` to prevent double-fire on fall-back.
- `last_fired` is keyed by ISO date in the reminder's stored timezone. Changing your `/reminder timezone` *after* a reminder fires today won't affect the dedup, but new reminders use the new zone going forward.
- Reminder text containing `@everyone`/`@here`/`@role` is rejected unless the creator has **Mention Everyone** in the target channel. Bots can't bypass the creator's own permissions for these mentions.
- Reminder data is global across every server the bot is in — the bot doesn't yet partition state per-guild.

## 🎀 $\color{#fda2f5}{\textbf{Authors}}$

- **@Pekkapost** — Bot Creator

Forked from the original [Narmaya Bot](https://github.com/Pekkapost/Narmaya-Bot) framework.
