# Stripchat Discord Monitor

A lightweight Discord bot that monitors selected Stripchat models and sends you a
direct message the moment one of them goes LIVE. It runs quietly in the
background 24/7 on a low cost VPS, using minimal CPU and bandwidth. Notifications
are sent only on the offline to live transition, so there is no spam or duplicate
alerts. Setup takes about five minutes.

---

![file](https://static.iimg.live/uploads/ultimate-photo-2669.png)



## Support the project

If this bot is useful to you, you can send a small gift:

**ETH:** `0xdAcfCfF1E567b4d15b1c8D88eC3c80aDb50017b2`


## Important notes

This version uses HTML parsing instead of the official Stripchat API.
Reason: the API endpoint (`/api/front/v2/models/.../cam`) is behind Cloudflare
and returns HTTP 418 for most datacenter and even some residential proxies.
The HTML page of the model loads fine, so the bot reads the status directly
from the rendered page.

Key implementation details:

- HTML is downloaded in streaming mode and parsing stops as soon as the status
  is found. This keeps proxy bandwidth usage low (usually 400-500 KB per check
  instead of the full page).
- `MAX_HTML_BYTES` controls the download limit per check. Default 600000 bytes.
  Lower values save bandwidth but may miss the status on some pages.
- No external captcha solver is used. Cloudflare challenge is bypassed by
  reading public HTML only.
- No viewer count. Only online/offline detection.
- Requires a residential or mobile proxy. Datacenter proxies (AWS, OVH,
  DigitalOcean, most cheap providers) are blocked by Cloudflare and will return
  418.

---

## Features

- Monitor multiple models simultaneously
- DM notifications when a model goes LIVE
- Quiet mode
- Proxy support (residential / mobile recommended)
- Low proxy bandwidth usage (streaming HTML with early exit)
- Owner-only commands

## Requirements

- Python 3.10+
- Discord bot token
- Residential or mobile proxy (required, datacenter IPs are blocked)

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
    CHECK_INTERVAL=1800
    MAX_HTML_BYTES=600000
    SESSION_ROTATE_EVERY=100
    HTTP_TIMEOUT=45

### Variables

| Variable | Description |
|---|---|
| `BOT_TOKEN` | Bot token from Discord Developer Portal |
| `USER_ID` | Discord ID of the DM recipient |
| `PROXY_URL` | Proxy URL. Required for Stripchat to return HTML 200 |
| `CHECK_INTERVAL` | Polling interval in seconds (min. 60, recommended 1800) |
| `MAX_HTML_BYTES` | Max bytes downloaded per check (default 600000) |
| `SESSION_ROTATE_EVERY` | Rotate HTTP session after N requests (default 100) |
| `HTTP_TIMEOUT` | Request timeout in seconds (default 45) |
| `MODELS` | Optional initial model list (fallback for `models.json`) |

## Running

    python app.py

On first start, `models.json` is created. Add models with the `!add` command.

## Commands

| Command | Description |
|---|---|
| `!add <name>` | Add a model |
| `!remove <name>` | Remove a model |
| `!list` | List monitored models with status |
| `!check` | Check all models now |
| `!test <name>` | Quick online/offline test |
| `!quiet on/off` | Toggle quiet mode |
| `!help` | Help |

## Proxy

Datacenter proxies (AWS, DigitalOcean, OVH, most cheap providers) are blocked
by Cloudflare for Stripchat. Use residential or mobile proxies.

Recommended: mobile 4G/LTE proxies. They are rarely blocked.

## License

[MIT](https://opensource.org/license/MIT)

