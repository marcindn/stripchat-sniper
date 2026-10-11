# -*- coding: utf-8 -*-
# Stripchat Discord Monitor - lightweight version.

import asyncio
import logging
import os
import re
import sys
import json
import time
import threading
import discord
from logging.handlers import RotatingFileHandler
from discord.ext import commands, tasks
from dotenv import load_dotenv

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    import requests as curl_requests

load_dotenv()


def _safe_int(v, d=0):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return d


# config
BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
USER_ID = _safe_int(os.getenv("USER_ID"), 0)
MODELS_ENV = [m.strip().lower() for m in (os.getenv("MODELS") or "").split(",") if m.strip()]
CHECK_INTERVAL = max(60, _safe_int(os.getenv("CHECK_INTERVAL"), 1800))

DATA_FILE = "models.json"
QUIET_FILE = "quiet.json"

PROXY_URL = (os.getenv("PROXY_URL") or "").strip()
PROXIES = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None

HTTP_TIMEOUT = _safe_int(os.getenv("HTTP_TIMEOUT"), 45)
MAX_HTML_BYTES = _safe_int(os.getenv("MAX_HTML_BYTES"), 600_000)
SESSION_ROTATE_EVERY = _safe_int(os.getenv("SESSION_ROTATE_EVERY"), 100)
NOTIFY_COOLDOWN = 900

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler("bot.log", maxBytes=2 * 1024 * 1024,
                            backupCount=2, encoding="utf-8"),
    ],
)
log = logging.getLogger("stripchat")


# file helpers
def load_models():
    if not os.path.exists(DATA_FILE):
        return MODELS_ENV.copy()
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        models = data.get("models") if isinstance(data, dict) else None
        if isinstance(models, list):
            return [str(m).strip().lower() for m in models if str(m).strip()]
        return MODELS_ENV.copy()
    except Exception as e:
        log.warning(f"load_models: {e}")
        return MODELS_ENV.copy()


def save_models(models_list):
    try:
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"models": models_list}, f, indent=4, ensure_ascii=False)
        os.replace(tmp, DATA_FILE)
    except Exception as e:
        log.error(f"save_models: {e}")


def load_quiet():
    if not os.path.exists(QUIET_FILE):
        return False
    try:
        with open(QUIET_FILE, "r", encoding="utf-8") as f:
            return bool(json.load(f).get("quiet", False))
    except Exception:
        return False


def save_quiet(state):
    try:
        tmp = QUIET_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"quiet": bool(state)}, f)
        os.replace(tmp, QUIET_FILE)
    except Exception as e:
        log.error(f"save_quiet: {e}")


# http session
_session_lock = threading.Lock()
_current_session = None
_session_req_count = 0


def _new_session():
    try:
        session = curl_requests.Session(impersonate="chrome")
    except Exception:
        session = curl_requests.Session()
    if PROXIES:
        try:
            session.proxies.update(PROXIES)
        except Exception:
            pass
    return session


def _get_session():
    global _current_session, _session_req_count
    with _session_lock:
        if _current_session is None or _session_req_count >= SESSION_ROTATE_EVERY:
            _current_session = _new_session()
            _session_req_count = 0
        _session_req_count += 1
        return _current_session


# status parsing
_ONLINE_STATUSES = ("public", "private", "group", "p2p", "virtual", "live", "online", "pornstar")


def _find_status_in_text(text, username):
    if not text:
        return None
    ul = username.lower()
    pat = re.compile(r'"username"\s*:\s*"' + re.escape(ul) + r'"', re.IGNORECASE)
    m = pat.search(text)
    if not m:
        return None

    window = text[m.start():m.start() + 4000].lower()

    im = re.search(r'"isonline"\s*:\s*(true|false)', window)
    if im:
        return im.group(1) == "true"

    lm = re.search(r'"islive"\s*:\s*(true|false)', window)
    if lm:
        return lm.group(1) == "true"

    sm = re.search(r'"status"\s*:\s*"(\w+)"', window)
    if sm:
        return sm.group(1).lower() in _ONLINE_STATUSES

    return None


def _stream_check(session, url, username):
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://stripchat.com/",
    }
    total = 0
    buf = ""
    r = None
    try:
        r = session.get(url, timeout=HTTP_TIMEOUT, headers=headers, stream=True)
        if r.status_code != 200:
            log.info(f"{username}: http {r.status_code} bytes=0")
            return None

        for chunk in r.iter_content(chunk_size=8192):
            if not chunk:
                continue
            total += len(chunk)
            try:
                buf += chunk.decode("utf-8", errors="ignore")
            except Exception:
                buf += chunk.decode("latin-1", errors="ignore")

            status = _find_status_in_text(buf, username)
            if status is not None:
                log.info(f"{username}: online={status} bytes={total}")
                return status

            if total >= MAX_HTML_BYTES:
                log.info(f"{username}: limit {MAX_HTML_BYTES} bytes, no status")
                return None

        log.info(f"{username}: full html {total} bytes, no status")
        return None
    except Exception as e:
        log.warning(f"{username}: {type(e).__name__}: {e} bytes={total}")
        return None
    finally:
        if r is not None:
            try:
                r.close()
            except Exception:
                pass


def is_model_online(username):
    username = (username or "").strip().lower()
    if not username:
        return False
    url = f"https://stripchat.com/{username}"
    session = _get_session()
    result = _stream_check(session, url, username)
    if result is None:
        return False
    return result


# discord bot
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents,
                   help_command=None, case_insensitive=True)

target_user = None
monitored_models = load_models()
last_status = {m: False for m in monitored_models}
quiet_mode = load_quiet()
last_notify = {}
_lock = asyncio.Lock()


@bot.event
async def on_ready():
    global target_user
    log.info(f"logged in as {bot.user}")
    log.info(f"models: {len(monitored_models)} interval: {CHECK_INTERVAL}s max_html: {MAX_HTML_BYTES}b")

    try:
        target_user = await bot.fetch_user(USER_ID)
    except Exception as e:
        log.critical(f"cannot fetch user {USER_ID}: {e}")
        await bot.close()
        return

    if not check_status.is_running():
        check_status.start()


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    await bot.process_commands(message)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, (commands.CommandNotFound, commands.NotOwner)):
        return
    log.error(f"cmd {ctx.command}: {error!r}")


async def _check_all():
    if not target_user:
        return
    async with _lock:
        for model in list(monitored_models):
            try:
                is_on = await asyncio.to_thread(is_model_online, model)
            except Exception as e:
                log.error(f"{model}: {e}")
                is_on = False

            was_on = last_status.get(model, False)
            last_status[model] = is_on

            if is_on and not was_on:
                log.info(f"{model} is now live")
                if not quiet_mode:
                    now = time.time()
                    if now - last_notify.get(model, 0) >= NOTIFY_COOLDOWN:
                        last_notify[model] = now
                        try:
                            await target_user.send(
                                f"**{model}** is now live\n"
                                f"https://stripchat.com/{model}"
                            )
                        except Exception as e:
                            log.error(f"dm error: {e}")
            elif not is_on and was_on:
                log.info(f"{model} went offline")


@tasks.loop(seconds=CHECK_INTERVAL)
async def check_status():
    await _check_all()


@check_status.before_loop
async def before_check():
    await bot.wait_until_ready()


# commands
@bot.command(name="add")
@commands.is_owner()
async def cmd_add(ctx, *, model: str):
    global monitored_models, last_status
    model = model.strip().lower()
    if not model or model in monitored_models:
        await ctx.send(f"`{model}` is already on the list.")
        return
    monitored_models.append(model)
    last_status[model] = False
    save_models(monitored_models)
    await ctx.send(f"added `{model}`. total: {len(monitored_models)}")


@bot.command(name="remove")
@commands.is_owner()
async def cmd_remove(ctx, *, model: str):
    global monitored_models, last_status
    model = model.strip().lower()
    if model not in monitored_models:
        await ctx.send(f"`{model}` is not on the list.")
        return
    monitored_models.remove(model)
    last_status.pop(model, None)
    save_models(monitored_models)
    await ctx.send(f"removed `{model}`. total: {len(monitored_models)}")


@bot.command(name="list")
@commands.is_owner()
async def cmd_list(ctx):
    if not monitored_models:
        await ctx.send("list is empty.")
        return
    txt = "\n".join(f"`{m}` - {'live' if last_status.get(m) else 'offline'}"
                    for m in monitored_models)
    await ctx.send(f"**monitored ({len(monitored_models)}):**\n{txt}")


@bot.command(name="test")
@commands.is_owner()
async def cmd_test(ctx, *, model: str):
    model = model.strip().lower()
    await ctx.send(f"checking `{model}`...")
    is_on = await asyncio.to_thread(is_model_online, model)
    await ctx.send(f"`{model}` -> {'live' if is_on else 'offline'}")


@bot.command(name="check")
@commands.is_owner()
async def cmd_check(ctx):
    await ctx.send("checking all...")
    await _check_all()
    live = [m for m in monitored_models if last_status.get(m)]
    if live:
        await ctx.send("live: " + ", ".join(f"`{m}`" for m in live))
    else:
        await ctx.send("no one is live.")


@bot.command(name="quiet")
@commands.is_owner()
async def cmd_quiet(ctx, state: str = None):
    global quiet_mode
    if state is None:
        await ctx.send(f"quiet mode: **{'on' if quiet_mode else 'off'}**")
        return
    if state.lower() in ("on", "1", "true", "yes"):
        quiet_mode = True
        save_quiet(True)
        await ctx.send("quiet mode on.")
    elif state.lower() in ("off", "0", "false", "no"):
        quiet_mode = False
        save_quiet(False)
        await ctx.send("quiet mode off.")
    else:
        await ctx.send("use `!quiet on` or `!quiet off`")


@bot.command(name="help")
@commands.is_owner()
async def cmd_help(ctx):
    await ctx.send(
        "**commands:**\n"
        "`!add <name>` - add model\n"
        "`!remove <name>` - remove model\n"
        "`!list` - list with status\n"
        "`!check` - check all now\n"
        "`!test <name>` - check one\n"
        "`!quiet on/off` - mute notifications"
    )


if __name__ == "__main__":
    if not BOT_TOKEN or USER_ID == 0:
        log.critical("missing BOT_TOKEN or USER_ID in .env")
        sys.exit(1)

    log.info(f"starting | models: {len(monitored_models)} | interval: {CHECK_INTERVAL}s")
    try:
        bot.run(BOT_TOKEN)
    except KeyboardInterrupt:
        log.info("stopped.")
    except Exception as e:
        log.critical(f"fatal: {e!r}")
        sys.exit(1)