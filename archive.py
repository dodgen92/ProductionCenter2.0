import os
import time
import threading
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load the .env file located alongside archive.py
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# =========================
# CONFIG
# =========================

CLIENT_ID = os.getenv("USER_CLIENT_ID")
ACCESS_TOKEN = os.getenv("USER_OAUTH_TOKEN")
BROADCASTER_ID = os.getenv("BROADCASTER_USER_ID")

CLIP_DURATION = 60
CLIP_INTERVAL = 30

CREATE_CLIP_URL = "https://api.twitch.tv/helix/clips"

# =========================
# CLIPPING STATE
# =========================

_stop_event = threading.Event()
_worker_thread = None
_lock = threading.Lock()


# =========================
# DISCORD WEBHOOK
# =========================

def post_clip_to_discord(clip_id):
    """Post a Twitch clip link to the configured Discord channel."""

    # Read the variable when posting, rather than relying on a
    # value captured when this module was imported.
    webhook_url = os.getenv("DISCORD_CLIP_WEBHOOK_URL")

    if not webhook_url:
        print("[Archive] ERROR: Discord webhook missing.")
        print(f"[Archive] Looking for .env at: {ENV_PATH}")
        print(
            "[Archive] DISCORD_CLIP_WEBHOOK_URL present in environment:",
            bool(os.getenv("DISCORD_CLIP_WEBHOOK_URL")),
        )
        return False

    clip_url = f"https://clips.twitch.tv/{clip_id}"

    payload = {
        "content": f"🎬 **New Twitch Clip**\n{clip_url}",
        "allowed_mentions": {"parse": []},
    }

    try:
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=10,
        )

        if response.status_code in (200, 204):
            print(f"[Archive] Posted clip to Discord: {clip_url}")
            return True

        print(
            f"[Archive] Discord webhook failed: "
            f"{response.status_code} - {response.text}"
        )
        return False

    except requests.RequestException as exc:
        print(f"[Archive] Discord notification error: {exc}")
        return False


# =========================
# TWITCH HELIX
# =========================

def create_clip():
    """Request a Twitch clip and notify Discord when accepted."""

    # Read Twitch credentials when called.
    client_id = os.getenv("USER_CLIENT_ID")
    access_token = os.getenv("USER_OAUTH_TOKEN")
    broadcaster_id = os.getenv("BROADCASTER_USER_ID")

    if not client_id or not access_token or not broadcaster_id:
        print("[Archive] ERROR: Missing Twitch credentials in .env")
        return False

    token = access_token.strip()

    if token.lower().startswith("oauth:"):
        token = token[6:]

    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {token}",
    }

    params = {
        "broadcaster_id": broadcaster_id,
        "duration": CLIP_DURATION,
    }

    try:
        response = requests.post(
            CREATE_CLIP_URL,
            headers=headers,
            params=params,
            timeout=15,
        )

        if response.status_code == 202:
            data = response.json().get("data", [])

            if not data:
                print(
                    "[Archive] Twitch accepted the request "
                    "but returned no clip ID."
                )
                return False

            clip = data[0]
            clip_id = clip.get("id")

            if not clip_id:
                print("[Archive] Twitch returned no clip ID.")
                return False

            clip_url = f"https://clips.twitch.tv/{clip_id}"

            print(f"[Archive] Clip requested: {clip_id}")
            print(f"[Archive] Clip URL: {clip_url}")

            edit_url = clip.get("edit_url")
            if edit_url:
                print(f"[Archive] Edit URL: {edit_url}")

            # A Discord failure won't stop the clipping loop.
            post_clip_to_discord(clip_id)

            return True

        print(
            f"[Archive] Clip request failed: "
            f"{response.status_code} - {response.text}"
        )
        return False

    except requests.RequestException as exc:
        print(f"[Archive] Twitch request error: {exc}")
        return False

    except ValueError as exc:
        print(f"[Archive] Invalid Twitch response: {exc}")
        return False


# =========================
# CLIPPING LOOP
# =========================

def _clip_loop():
    print("[Archive] Automatic clipping STARTED.")

    try:
        while not _stop_event.is_set():
            create_clip()

            # Stop immediately rather than waiting out the interval.
            if _stop_event.wait(CLIP_INTERVAL):
                break

    finally:
        print("[Archive] Automatic clipping STOPPED.")

        global _worker_thread
        with _lock:
            if _worker_thread is threading.current_thread():
                _worker_thread = None


# =========================
# PUBLIC START / STOP
# =========================

def start_archiving():
    """Start automatic clipping; ignore duplicate Start requests."""

    global _worker_thread

    with _lock:
        if _worker_thread is not None and _worker_thread.is_alive():
            print("[Archive] Already running; ignoring Start.")
            return

        _stop_event.clear()

        _worker_thread = threading.Thread(
            target=_clip_loop,
            name="TwitchClipArchive",
            daemon=True,
        )

        _worker_thread.start()


def stop_archiving():
    """Stop automatic clipping."""

    with _lock:
        if _worker_thread is None or not _worker_thread.is_alive():
            print("[Archive] Not running.")
            return

        _stop_event.set()

    print("[Archive] Stop requested.")


def is_archiving():
    """Return whether the clipping loop is running."""

    with _lock:
        return (
            _worker_thread is not None
            and _worker_thread.is_alive()
            and not _stop_event.is_set()
        )


# =========================
# OPTIONAL STANDALONE TEST
# =========================

if __name__ == "__main__":
    try:
        start_archiving()

        while is_archiving():
            time.sleep(1)

    except KeyboardInterrupt:
        stop_archiving()

