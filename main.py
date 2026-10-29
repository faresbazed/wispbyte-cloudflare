#!/usr/bin/env python3
"""
Wispbyte Xray + Cloudflare Tunnel launcher.

Required environment variable:
  CLOUDFLARE_TUNNEL_TOKEN  Cloudflare Tunnel token (rotate it if previously exposed)

Optional environment variables:
  VLESS_UUID               Default: 00000000-0000-4000-8000-000000000123
  WS_PATH                  Default: /vless
  XRAY_PORT                Default: 10000
  TUNNEL_HOSTNAME          Default: wis.faresbazed.web.id
  XRAY_VERSION             Default: latest
  CLOUDFLARED_VERSION      Default: latest
  TUNNEL_PROTOCOL          Default: http2 (use "quic" to revert)
"""

import json
import os
import platform
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

BASE_DIR = Path("/home/container")
if not BASE_DIR.exists():
    BASE_DIR = Path.cwd()


def load_dotenv(env_path):
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            os.environ.setdefault(key, value)


load_dotenv(BASE_DIR / ".env")

XRAY_BIN = BASE_DIR / "xray"
CLOUDFLARED_BIN = BASE_DIR / "cloudflared"
XRAY_CONFIG = BASE_DIR / "xray-config.json"

TOKEN = os.environ.get("CLOUDFLARE_TUNNEL_TOKEN", "").strip()
UUID = os.environ.get("VLESS_UUID", "00000000-0000-4000-8000-000000000123").strip()
WS_PATH = os.environ.get("WS_PATH", "/vless").strip()
XRAY_PORT = int(os.environ.get("XRAY_PORT", "10000"))
HOSTNAME = os.environ.get("TUNNEL_HOSTNAME", "wis.faresbazed.web.id").strip()
TUNNEL_PROTOCOL = os.environ.get("TUNNEL_PROTOCOL", "http2").strip().lower()
XRAY_VERSION = os.environ.get("XRAY_VERSION", "latest").strip()
CLOUDFLARED_VERSION = os.environ.get("CLOUDFLARED_VERSION", "latest").strip()

children = []
stopping = False


def log(message):
    print(f"[setup] {message}", flush=True)


def fetch_json(url):
    request = urllib.request.Request(
        url, headers={"User-Agent": "wispbyte-xray-launcher/1.0"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def download(url, destination):
    log(f"Downloading {destination.name}...")
    request = urllib.request.Request(
        url, headers={"User-Agent": "wispbyte-xray-launcher/1.0"}
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        with open(destination, "wb") as output:
            shutil.copyfileobj(response, output)


def ensure_xray():
    if XRAY_BIN.is_file():
        XRAY_BIN.chmod(XRAY_BIN.stat().st_mode | stat.S_IXUSR)
        return

    system = platform.system().lower()
    machine = platform.machine().lower()
    if system != "linux" or machine not in ("x86_64", "amd64"):
        raise RuntimeError(f"Unsupported platform for this script: {system}/{machine}")

    if XRAY_VERSION == "latest":
        release = fetch_json("https://api.github.com/repos/XTLS/Xray-core/releases/latest")
        version = release["tag_name"]
    else:
        version = XRAY_VERSION if XRAY_VERSION.startswith("v") else f"v{XRAY_VERSION}"

    asset_url = (
        "https://github.com/XTLS/Xray-core/releases/download/"
        f"{version}/Xray-linux-64.zip"
    )
    archive = BASE_DIR / "xray-download.zip"
    download(asset_url, archive)

    with zipfile.ZipFile(archive) as zf:
        member = next((n for n in zf.namelist() if Path(n).name == "xray"), None)
        if member is None:
            raise RuntimeError("The Xray release archive did not contain the xray binary.")
        with zf.open(member) as source, open(XRAY_BIN, "wb") as destination:
            shutil.copyfileobj(source, destination)

    archive.unlink(missing_ok=True)
    XRAY_BIN.chmod(0o755)
    log(f"Installed Xray {version}.")


def ensure_cloudflared():
    if CLOUDFLARED_BIN.is_file():
        CLOUDFLARED_BIN.chmod(CLOUDFLARED_BIN.stat().st_mode | stat.S_IXUSR)
        return

    if CLOUDFLARED_VERSION == "latest":
        url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
    else:
        version = CLOUDFLARED_VERSION
        if not version.startswith("202"):
            version = f"{version}"
        url = (
            "https://github.com/cloudflare/cloudflared/releases/download/"
            f"{version}/cloudflared-linux-amd64"
        )

    download(url, CLOUDFLARED_BIN)
    CLOUDFLARED_BIN.chmod(0o755)
    log("Installed cloudflared.")


def write_xray_config():
    if not UUID:
        raise RuntimeError("VLESS_UUID cannot be empty.")
    if not WS_PATH.startswith("/"):
        raise RuntimeError("WS_PATH must begin with '/'.")

    config = {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "listen": "127.0.0.1",
                "port": XRAY_PORT,
                "protocol": "vless",
                "settings": {
                    "clients": [{"id": UUID, "email": "wispbyte-user"}],
                    "decryption": "none",
                },
                "streamSettings": {
                    "network": "ws",
                    "wsSettings": {"path": WS_PATH},
                },
                "sniffing": {
                    "enabled": True,
                    "destOverride": ["http", "tls"],
                },
            }
        ],
        "outbounds": [
            {"protocol": "freedom", "tag": "direct"},
            {"protocol": "blackhole", "tag": "block"},
        ],
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [
                {"type": "field", "protocol": ["bittorrent"], "outboundTag": "block"}
            ],
        },
    }
    XRAY_CONFIG.write_text(json.dumps(config, indent=2), encoding="utf-8")


def terminate_children():
    global stopping
    stopping = True
    for process in children:
        if process.poll() is None:
            try:
                process.terminate()
            except Exception:
                pass
    deadline = time.time() + 8
    for process in children:
        if process.poll() is None:
            try:
                process.wait(timeout=max(0.1, deadline - time.time()))
            except subprocess.TimeoutExpired:
                process.kill()


def signal_handler(signum, _frame):
    log(f"Received signal {signum}; stopping processes.")
    terminate_children()


def main():
    if not TOKEN:
        log("ERROR: Set CLOUDFLARE_TUNNEL_TOKEN in the Wispbyte server environment.")
        return 1
    if TUNNEL_PROTOCOL not in ("http2", "quic", "auto"):
        log("ERROR: TUNNEL_PROTOCOL must be http2, quic, or auto.")
        return 1

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        ensure_xray()
        ensure_cloudflared()
        write_xray_config()

        # Validate config before launching the long-running process.
        check = subprocess.run(
            [str(XRAY_BIN), "run", "-test", "-config", str(XRAY_CONFIG)],
            cwd=str(BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=30,
        )
        if check.returncode != 0:
            log("ERROR: Xray configuration validation failed:")
            print(check.stdout, flush=True)
            return check.returncode

        log(f"VLESS UUID: {UUID}")
        log(f"WebSocket path: {WS_PATH}")
        log(f"Xray local listener: 127.0.0.1:{XRAY_PORT}")
        log(f"Tunnel hostname: {HOSTNAME}")
        log(f"Cloudflare transport: {TUNNEL_PROTOCOL}")
        log("Starting Xray...")

        xray = subprocess.Popen(
            [str(XRAY_BIN), "run", "-config", str(XRAY_CONFIG)],
            cwd=str(BASE_DIR),
        )
        children.append(xray)

        # Wait briefly and fail clearly if Xray exits immediately.
        time.sleep(1)
        if xray.poll() is not None:
            log(f"ERROR: Xray exited immediately with code {xray.returncode}.")
            return xray.returncode or 1

        log("Starting Cloudflare Tunnel...")
        tunnel_cmd = [
            str(CLOUDFLARED_BIN),
            "tunnel",
            "--no-autoupdate",
            "--protocol",
            TUNNEL_PROTOCOL,
            "run",
            "--token",
            TOKEN,
        ]
        cloudflared = subprocess.Popen(tunnel_cmd, cwd=str(BASE_DIR))
        children.append(cloudflared)
        log("Xray and cloudflared started. Monitoring both processes.")

        while not stopping:
            xray_code = xray.poll()
            tunnel_code = cloudflared.poll()

            if xray_code is not None:
                log(f"ERROR: Xray exited with code {xray_code}; stopping tunnel.")
                return xray_code or 1
            if tunnel_code is not None:
                log(
                    f"ERROR: cloudflared exited with code {tunnel_code}; "
                    "stopping Xray. Check token, tunnel status, and logs above."
                )
                return tunnel_code or 1
            time.sleep(2)

        return 0
    except urllib.error.HTTPError as exc:
        log(f"ERROR: Download/update request failed: HTTP {exc.code} for {exc.url}")
        return 1
    except urllib.error.URLError as exc:
        log(f"ERROR: Network/download error: {exc}")
        return 1
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, tarfile.TarError) as exc:
        log(f"ERROR: {exc}")
        return 1
    except subprocess.TimeoutExpired:
        log("ERROR: Xray configuration test timed out.")
        return 1
    finally:
        terminate_children()


if __name__ == "__main__":
    sys.exit(main())
