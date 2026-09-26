# Stripchat Discord Monitor

Discord bot that monitors selected Stripchat models and sends DM notifications
when a stream goes LIVE.

## Features

- Monitor multiple models simultaneously
- DM notifications when a model goes LIVE
- Editable status embed
- Quiet mode
- Proxy support (residential / mobile)
- Retry, backoff, and cooldown after rate limits
- Owner-only commands

## Requirements

- Python 3.10+
- Discord bot token
- (Recommended) residential/mobile proxy

## Installation

    git clone https://github.com/marcindn/stripchat-monitor.git
    cd stripchat-monitor
    pip install -r requirements.txt

## Configuration

Copy `.env.example` to `.env` and fill in your values:

    cp .env.example .env

Then edit `.env`:

    BOT_TOKEN=your_token
    USER_ID=your_id
    PROXY_URL=http://user:pass@host:port
    CHECK_INTERVAL=60
    SEND_LIVE_NOTIFY=1

### Variables

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Bot token from Discord Developer Portal |
| `USER_ID` | Discord ID of the DM recipient |
| `PROXY_URL` | Proxy URL. Without it, Stripchat API returns 403 |
| `CHECK_INTERVAL` | Polling interval in seconds (min. 15, recommended 120-180) |
| `SEND_LIVE_NOTIFY` | `1` enabled, `0` disabled |
| `MODELS` | Optional model list (fallback for `models.json`) |

## Running

    python app.py

On first start, `models.json` is created. Add models with the `!add` command.

## Commands

| Command | Description |
|---|---|
| `!add <name>` | Add a model |
| `!remove <name>` | Remove a model |
| `!list` | List monitored models |
| `!online` | Currently LIVE models |
| `!status [name]` | Model status / refresh embed |
| `!test <name>` | Quick live/offline test |
| `!quiet on/off` | Toggle quiet mode |
| `!help` | Help |

## Proxy

Interactive configurator:

    python setup_proxy.py

The script checks your IP, tests the proxy and the Stripchat API, then saves
`PROXY_URL` to `.env`.

Requirements:

- Use residential or mobile proxies
- Do not use free proxies or datacenter IPs (AWS, DigitalOcean, OVH)

## License

MIT
