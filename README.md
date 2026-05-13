# PekkaBot2

A personal Discord bot for the *Granblue Fantasy: Relink* (GBFR) community. Provides quick links to community character guides, an FAQ menu, and a recurring weekly reminder system.

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
- **Message Content Intent** — required for prefix commands (`p!narmaya`, etc.) to read message text.

When inviting the bot to a server, include both the `bot` and `applications.commands` scopes so slash commands appear.

### 3. Database.json

Character guides and FAQ entries are read from [`src/Database.json`](src/Database.json). The structure is:

```jsonc
{
  "characters": {
    "narmaya": {
      "help":    "Help text shown by p!help",
      "color":   "0xff0000",       // hex string used for embed color
      "guide":   "https://...",     // link to the guide thread
      "channel": "https://...",     // link to the discussion channel
      "image":   "https://..."      // optional thumbnail
    }
  },
  "faqdata": {
    "sigildrops": {
      "title": "Sigil Drop Table",
      "data":  "Embed body text",
      "help":  "Help text shown by p!help",
      "link":  "https://...",       // optional, becomes embed URL
      "image": "https://..."        // optional thumbnail
    }
  }
}
```

Adding a new character key automatically registers a new prefix command (e.g. `p!newchar`) on next start. FAQ topics need a corresponding entry in [`FAQ_COMMANDS`](src/cogs/Menu.py) to register a prefix command.

### 4. Reminders.json

Auto-created at `src/Reminders.json` the first time `/reminder add` runs. No manual setup needed.

### 5. Run

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
| [src/cogs/Characters.py](src/cogs/Characters.py) | Per-character guide commands plus `/guide` slash command. Commands are generated dynamically from `Database.json`. |
| [src/cogs/Menu.py](src/cogs/Menu.py) | FAQ commands plus `/faq` slash command. Commands are generated from a config list in the file. |
| [src/cogs/Reminders.py](src/cogs/Reminders.py) | `/reminder` slash command group for recurring weekly reminders, with persistence in `src/Reminders.json`. |
| [src/Database.json](src/Database.json) | All character and FAQ data. |

## Commands

The configured prefix is `p!`. Slash commands are also globally synced on startup.

### Characters

Each character has a prefix command equal to its name. All post two embeds: the guide link and the discussion channel link.

| Command | Aliases | Description |
|---|---|---|
| `p!narmaya` | — | Narmaya guide + channel |
| `p!io` | — | Io guide + channel |
| `p!captain` | `p!gran`, `p!djeeta` | Captain guide + channel |
| `p!katalina` | — | Katalina guide + channel |
| `p!rackam` | — | Rackam guide + channel |
| `p!eugen` | — | Eugen guide + channel |
| `p!rosetta` | — | Rosetta guide + channel |
| `p!ferry` | — | Ferry guide + channel |
| `p!lancelot` | — | Lancelot guide + channel |
| `p!percival` | — | Percival guide + channel |
| `p!vane` | — | Vane guide + channel |
| `p!siegfried` | — | Siegfried guide + channel |
| `p!charlotta` | — | Charlotta guide + channel |
| `p!yodarha` | — | Yodarha guide + channel |
| `p!zeta` | — | Zeta guide + channel |
| `p!vaseraga` | — | Vaseraga guide + channel |
| `p!cagliostro` | — | Cagliostro guide + channel |
| `p!ghandagoza` | — | Ghandagoza guide + channel |
| `p!id` | — | Id guide + channel |
| `p!seofon` | — | Seofon guide + channel |
| `p!tweyen` | — | Tweyen guide + channel |
| `p!sandalphon` | — | Sandalphon guide + channel |
| `/guide character:<name>` | — | Slash command equivalent with autocomplete. |

### FAQ

| Command | Aliases | Description |
|---|---|---|
| `p!sigil_drop_table` | `p!sigildroptable`, `p!sigil_drop`, `p!sigildrop` | Sigil drop rate table |
| `p!afk` | — | AFK farming guide |
| `p!damage_calculator` | `p!damagecalculator`, `p!calculator`, `p!calc`, `p!damagecalc`, `p!dmgcalc` | Damage calculator link |
| `p!quest_rate_table` | `p!questratetabe`, `p!questrate`, `p!quest_rate`, `p!questdrops`, `p!quest_drops` | Quest drop rate table |
| `p!curio_drop_table` | `p!curiodroptable`, `p!curio_drop`, `p!curiodrop` | Curio drop rate table |
| `p!dps_meter` | `p!dpsmeter`, `p!dps`, `p!skill_issue`, `p!skillissue` | DPS meter install link |
| `p!damage_cap` | `p!damagecap`, `p!dmgcap`, `p!cap` | Damage cap guide |
| `p!awakening` | — | Awakening+ explanation |
| `p!pins` | `p!pin` | Tells the user to read the pinned messages |
| `/faq topic:<name>` | — | Slash command equivalent with autocomplete. |

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
