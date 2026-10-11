# -*- coding: utf-8 -*-
# Interactive proxy setup for stripchat-sniper.
# Validates format, tests IP and HTML page load, saves PROXY_URL to .env.

import os
import re
import sys
import shutil
import urllib.parse

try:
    from curl_cffi import requests as http_requests
    _IMPERSONATE = "chrome"
    _HTTP_BACKEND = "curl_cffi"
except ImportError:
    try:
        import requests as http_requests
        _IMPERSONATE = None
        _HTTP_BACKEND = "requests"
    except ImportError:
        print("[X] missing curl_cffi and requests. install: pip install curl_cffi requests")
        sys.exit(1)

ENV_FILE = ".env"
IPIFY_URL = "https://api.ipify.org?format=json"
STRIPCHAT_TEST_URL = "https://stripchat.com/testmodelnotexist"


def green(s):  return f"\033[0;32m{s}\033[0m"
def red(s):    return f"\033[0;31m{s}\033[0m"
def yellow(s): return f"\033[1;33m{s}\033[0m"
def cyan(s):   return f"\033[0;36m{s}\033[0m"


def _http_get(url, proxies=None, timeout=15, headers=None):
    kwargs = {"timeout": timeout}
    if headers:
        kwargs["headers"] = headers
    if proxies:
        kwargs["proxies"] = proxies
    if _IMPERSONATE:
        kwargs["impersonate"] = _IMPERSONATE
    return http_requests.get(url, **kwargs)


def ask(prompt, default=None, required=True):
    while True:
        suffix = f" [{default}]" if default else ""
        val = input(f"{prompt}{suffix}: ").strip()
        if not val and default:
            return default
        if not val and required:
            print("  value required.")
            continue
        return val


def ask_choice(prompt, choices, default=None):
    while True:
        val = input(f"{prompt} {'/'.join(choices)}"
                    + (f" [{default}]: " if default else ": ")).strip().lower()
        if not val and default:
            return default
        if val in choices:
            return val
        print(f"  choose one of: {', '.join(choices)}")


def validate_host(h):
    if not h:
        return False
    return bool(re.match(r"^[a-zA-Z0-9\.\-_]+$", h))


def validate_port(p):
    try:
        i = int(p)
        return 1 <= i <= 65535
    except (TypeError, ValueError):
        return False


def build_proxy_url(scheme, host, port, user=None, password=None):
    if user:
        auth = f"{urllib.parse.quote(user, safe='')}:{urllib.parse.quote(password, safe='')}@"
    else:
        auth = ""
    return f"{scheme}://{auth}{host}:{port}"


def test_ip(proxy_url, timeout=15):
    proxies = {"http": proxy_url, "https": proxy_url}
    try:
        r = _http_get(IPIFY_URL, proxies=proxies, timeout=timeout)
        if r.status_code == 200:
            return r.json().get("ip")
        return None
    except Exception as e:
        print(f"  error: {e}")
        return None


def test_direct_ip(timeout=10):
    try:
        r = _http_get(IPIFY_URL, timeout=timeout)
        if r.status_code == 200:
            return r.json().get("ip")
    except Exception:
        pass
    return None


def test_stripchat_html(proxy_url, timeout=30):
    proxies = {"http": proxy_url, "https": proxy_url}
    headers = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://stripchat.com/",
    }
    try:
        r = _http_get(STRIPCHAT_TEST_URL, proxies=proxies, timeout=timeout, headers=headers)
        return r.status_code
    except Exception as e:
        print(f"  error: {e}")
        return None


def write_env(updates: dict):
    if os.path.exists(ENV_FILE):
        try:
            shutil.copy2(ENV_FILE, ENV_FILE + ".bak")
            try:
                os.chmod(ENV_FILE + ".bak", 0o600)
            except Exception:
                pass
        except Exception:
            pass

    lines = []
    seen = set()
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.rstrip("\n")
                if "=" in stripped and not stripped.lstrip().startswith("#"):
                    k = stripped.split("=", 1)[0].strip()
                    if k in updates:
                        lines.append(f"{k}={updates[k]}\n")
                        seen.add(k)
                        continue
                lines.append(line if line.endswith("\n") else line + "\n")

    for k, v in updates.items():
        if k not in seen:
            lines.append(f"{k}={v}\n")

    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)

    try:
        os.chmod(ENV_FILE, 0o600)
    except Exception:
        pass


def main():
    print(cyan("=" * 60))
    print(cyan(" setup_proxy.py - proxy configuration"))
    print(cyan(f" http backend: {_HTTP_BACKEND}"
               + (f" (impersonate={_IMPERSONATE})" if _IMPERSONATE else "")))
    print(cyan("=" * 60))

    print("\n[1/5] checking your current IP (direct)...")
    direct_ip = test_direct_ip()
    if direct_ip:
        print(f"      your IP: {yellow(direct_ip)}")
    else:
        print(yellow("      could not detect IP (may be blocked)"))

    print("\n[2/5] proxy details:")
    scheme = ask_choice("proxy type (http/socks5/socks4)", ["http", "socks5", "socks4"], "http")

    host = ""
    while not validate_host(host):
        host = ask("host (e.g. proxy.example.com)")
        if not validate_host(host):
            print("  invalid host.")

    port = ""
    while not validate_port(port):
        port = ask("port (1-65535)")
        if not validate_port(port):
            print("  invalid port.")

    use_auth = ask_choice("does the proxy require auth? (y/n)", ["y", "n"], "y") == "y"
    user = password = None
    if use_auth:
        user = ask("username")
        password = ask("password")

    proxy_url = build_proxy_url(scheme, host, port, user, password)
    masked = re.sub(r"://[^@]+@", "://***:***@", proxy_url)
    print(f"\n      PROXY_URL = {yellow(masked)}")

    print("\n[3/5] testing IP through proxy...")
    proxied_ip = test_ip(proxy_url)
    if not proxied_ip:
        print(red("      proxy not responding."))
        print("      tips:")
        print("      - check host/port/login/password")
        print("      - for socks5 install: pip install 'requests[socks]'")
        print("      - proxy may require IP whitelist")
        sys.exit(2)
    print(f"      proxy IP: {green(proxied_ip)}")

    if direct_ip and proxied_ip == direct_ip:
        print(yellow("      IP did not change - proxy may not be working."))

    print("\n[4/5] testing Stripchat HTML page through proxy...")
    code = test_stripchat_html(proxy_url)
    print(f"      HTTP: {code}")
    ok_status = code in (200, 404)

    if ok_status:
        print(green(f"      proxy works with Stripchat (status {code})"))
    else:
        print(red(f"      Stripchat returns {code} - proxy is blocked or not working"))

    print("\n[5/5] saving PROXY_URL to .env...")
    if not os.path.exists(ENV_FILE):
        write_env({
            "PROXY_URL": proxy_url,
            "BOT_TOKEN": "",
            "USER_ID": "",
            "CHECK_INTERVAL": "1800",
            "MAX_HTML_BYTES": "600000",
            "SESSION_ROTATE_EVERY": "100",
            "HTTP_TIMEOUT": "45",
        })
    else:
        write_env({"PROXY_URL": proxy_url})
    print(green("      saved (backup: .env.bak)"))

    print("\n" + cyan("summary"))
    print(f"      direct IP:   {direct_ip}")
    print(f"      proxy IP:    {proxied_ip}")
    print(f"      Stripchat:   {code}")
    if ok_status:
        print(green("\n  proxy works - restart the bot: python3 app.py"))
    else:
        print(red("\n  proxy does not work with Stripchat"))
        print("  tips:")
        print("  - use residential or mobile proxy (not datacenter)")
        print("  - try mobile 4G/LTE - rarely blocked")
        sys.exit(3)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\ninterrupted.")
        sys.exit(1)
