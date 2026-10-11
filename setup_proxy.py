# -*- coding: utf-8 -*-
"""
setup_proxy.py — interaktywny konfigurator proxy dla bota Stripchat.
- pyta o dane proxy
- waliduje format
- testuje IP (api.ipify.org)
- testuje Stripchat API (czy zwraca 200 zamiast 418/403)
- zapisuje PROXY_URL do .env (bezpiecznie, nie nadpisując innych zmiennych)
"""

import os
import re
import sys
import shutil
import urllib.parse

# [FIX] Preferuj curl_cffi (z impersonate) jeśli dostępne — test proxy
# odzwierciedla realne połączenie bota, brak fałszywych negatywów przy CF.
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
        print("[X] Brak 'curl_cffi' ani 'requests'. Zainstaluj: pip install curl_cffi requests")
        sys.exit(1)

ENV_FILE = ".env"
IPIFY_URL = "https://api.ipify.org?format=json"
STRIPCHAT_TEST_URL = "https://stripchat.com/api/front/v2/models/username/test/cam"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "application/json"}


def green(s):  return f"\033[0;32m{s}\033[0m"
def red(s):    return f"\033[0;31m{s}\033[0m"
def yellow(s): return f"\033[1;33m{s}\033[0m"
def cyan(s):   return f"\033[0;36m{s}\033[0m"


def _http_get(url, proxies=None, timeout=15, headers=None):
    """Wrapper: używa curl_cffi jeśli dostępne, inaczej requests."""
    kwargs = {"timeout": timeout, "headers": headers or HEADERS}
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
            print("  ↳ Wartość wymagana.")
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
        print(f"  ↳ Wybierz jedną z: {', '.join(choices)}")


def validate_host(h):
    if not h:
        return False
    # host: domena lub IP
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
        print(f"  ↳ błąd: {e}")
        return None


def test_direct_ip(timeout=10):
    try:
        r = _http_get(IPIFY_URL, timeout=timeout)
        if r.status_code == 200:
            return r.json().get("ip")
    except Exception:
        pass
    return None


def test_stripchat(proxy_url, timeout=20):
    proxies = {"http": proxy_url, "https": proxy_url}
    try:
        r = _http_get(STRIPCHAT_TEST_URL, proxies=proxies, timeout=timeout)
        return r.status_code
    except Exception as e:
        print(f"  ↳ błąd: {e}")
        return None


def read_env():
    if not os.path.exists(ENV_FILE):
        return {}
    out = {}
    with open(ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line or line.lstrip().startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v
    return out


def write_env(updates: dict):
    """
    Bezpiecznie aktualizuje .env — zachowuje inne zmienne i komentarze.
    [FIX] Backup robiony PRZED modyfikacją (kopiujemy oryginał, nie nową treść).
    """
    # 1) Prawdziwy backup — kopia oryginalnego pliku przed modyfikacją
    if os.path.exists(ENV_FILE):
        try:
            shutil.copy2(ENV_FILE, ENV_FILE + ".bak")
            try:
                os.chmod(ENV_FILE + ".bak", 0o600)
            except Exception:
                pass
        except Exception:
            pass

    # 2) Odczyt + podmiana wpisów
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

    # dopisz brakujące
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
    print(cyan(" setup_proxy.py — konfiguracja proxy"))
    print(cyan(f" backend HTTP: {_HTTP_BACKEND}"
               + (f" (impersonate={_IMPERSONATE})" if _IMPERSONATE else "")))
    print(cyan("=" * 60))

    # --- 1. Wykryj obecne IP (bez proxy) ---
    print("\n[1/6] Sprawdzam Twoje obecne IP (bez proxy)...")
    direct_ip = test_direct_ip()
    if direct_ip:
        print(f"      Twoje IP: {yellow(direct_ip)}")
    else:
        print(yellow("      Nie udało się ustalić IP (może być już blokada)"))

    # --- 2. Zbierz dane proxy ---
    print("\n[2/6] Podaj dane proxy:")
    scheme = ask_choice("Typ proxy (http/socks5/socks4)", ["http", "socks5", "socks4"], "http")

    host = ""
    while not validate_host(host):
        host = ask("Adres hosta (np. proxy.example.com)")
        if not validate_host(host):
            print("  ↳ Nieprawidłowy host.")

    port = ""
    while not validate_port(port):
        port = ask("Port (1-65535)")
        if not validate_port(port):
            print("  ↳ Nieprawidłowy port.")

    use_auth = ask_choice("Czy proxy wymaga logowania? (t/n)", ["t", "n"], "t") == "t"
    user = password = None
    if use_auth:
        user = ask("Login")
        password = ask("Hasło")

    proxy_url = build_proxy_url(scheme, host, port, user, password)
    # zamaskowana wersja do wyświetlenia
    masked = re.sub(r"://[^@]+@", "://***:***@", proxy_url)
    print(f"\n      PROXY_URL = {yellow(masked)}")

    # --- 3. Test IP przez proxy ---
    print("\n[3/6] Testuję IP przez proxy (api.ipify.org)...")
    proxied_ip = test_ip(proxy_url)
    if not proxied_ip:
        print(red("      ✗ Proxy nie odpowiada lub nie działa."))
        print("      Wskazówki:")
        print("      • Sprawdź host/port/login/hasło")
        print("      • Dla socks5 zainstaluj: pip install 'requests[socks]'")
        print("      • Upewnij się, że proxy nie wymaga IP whitelistingu")
        sys.exit(2)

    print(f"      IP przez proxy: {green(proxied_ip)}")

    if direct_ip and proxied_ip == direct_ip:
        print(yellow("      ⚠ IP się NIE zmieniło — proxy może nie działać poprawnie."))

    # --- 4. Test Stripchat API przez proxy ---
    print("\n[4/6] Testuję Stripchat API przez proxy...")
    code = test_stripchat(proxy_url)
    print(f"      HTTP: {code}")

    ok_status = code in (200, 404)  # 404 = model 'test' nie istnieje, ale API odpowiada
    if ok_status:
        print(green(f"      ✓ Proxy działa z API Stripchat (status {code})"))
    else:
        print(red(f"      ✗ API zwraca {code} — proxy też jest blokowane lub coś nie działa"))

    # --- 5. Zapisz do .env ---
    print("\n[5/6] Zapisuję PROXY_URL do .env...")
    if not os.path.exists(ENV_FILE):
        print(yellow("      .env nie istnieje — utworzę minimalny"))
        write_env({"PROXY_URL": proxy_url,
                   "BOT_TOKEN": "",
                   "USER_ID": "",
                   "MODELS": "",
                   "CHECK_INTERVAL": "300",
                   "SEND_LIVE_NOTIFY": "1"})
    else:
        write_env({"PROXY_URL": proxy_url})
    print(green("      ✓ Zapisano (backup: .env.bak)"))

    # --- 6. Podsumowanie ---
    print("\n[6/6] " + cyan("PODSUMOWANIE"))
    print(f"      IP bez proxy:    {direct_ip}")
    print(f"      IP przez proxy:  {proxied_ip}")
    print(f"      Stripchat test:  {code}")
    if ok_status:
        print(green("\n  ✓ PROXY DZIAŁA — zrestartuj bota: python3 app.py"))
    else:
        print(red("\n  ✗ PROXY NIE DZIAŁA z API Stripchat"))
        print("  Wskazówki:")
        print("  • Spróbuj proxy rezydencjonalnego (nie datacenter)")
        print("  • Niektóre proxy mobilne (4G) są mniej wykrywalne")
        print("  • Sprawdź czy proxy nie jest już na blackliście CF")
        sys.exit(3)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nPrzerwano.")
        sys.exit(1)