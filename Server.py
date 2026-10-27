import os
import sys
import json
import time
import subprocess
import threading
from threading import Thread
from pathlib import Path
import requests
from dotenv import load_dotenv
from flask import Flask, request, jsonify

from Pokemon.pokerip import catch_pokemon

# =============================
# CONFIGURATION
# =============================

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_OAUTH_TOKEN = os.getenv("TWITCH_OAUTH_TOKEN")
BROADCASTER_USER_ID = os.getenv("BROADCASTER_USER_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
SECRET = os.getenv("SECRET")

ARCHIVE_SCRIPT = BASE_DIR / "archive.py"

app = Flask(__name__)

# =============================
# ARCHIVE PROCESS MANAGEMENT
# =============================

archive_process = None
archive_lock = threading.Lock()


def run_archive():
    """Launch archive.py as a separate process."""

    global archive_process

    with archive_lock:
        if archive_process is not None and archive_process.poll() is None:
            print("[Server] Archive is already running.")
            return

        if not ARCHIVE_SCRIPT.is_file():
            print(f"[Server] ERROR: Cannot find {ARCHIVE_SCRIPT}")
            return

        try:
            archive_process = subprocess.Popen(
                [sys.executable, str(ARCHIVE_SCRIPT)],
                cwd=str(BASE_DIR),
            )

            print(
                f"[Server] Archive launched. PID: {archive_process.pid}"
            )

        except Exception as exc:
            archive_process = None
            print(f"[Server] Failed to launch archive.py: {exc}")


def start_archive_thread():
    """Launch the archive process without blocking EventSub."""

    Thread(target=run_archive, daemon=True).start()


def stop_archive():
    """Stop the archive.py process."""

    global archive_process

    with archive_lock:
        if archive_process is None:
            print("[Server] Archive is not running.")
            return

        if archive_process.poll() is not None:
            print("[Server] Archive has already stopped.")
            archive_process = None
            return

        try:
            print("[Server] Stopping archive.py...")
            archive_process.terminate()

            try:
                archive_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("[Server] Force-stopping archive.py...")
                archive_process.kill()
                archive_process.wait(timeout=5)

            print("[Server] Archive stopped.")

        except Exception as exc:
            print(f"[Server] Error stopping archive.py: {exc}")

        finally:
            archive_process = None


# =============================
# CAMERA FILTER
# =============================

def run_camera_filter():
    subprocess.run(
        [sys.executable, str(BASE_DIR / "CameraFilters" / "Filter.py")],
        cwd=str(BASE_DIR),
    )

    time.sleep(180)

    subprocess.run(
        [
            sys.executable,
            str(BASE_DIR / "CameraFilters" / "clearfilter.py"),
        ],
        cwd=str(BASE_DIR),
    )


# =============================
# EVENTSUB WEBHOOK
# =============================

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json or {}

    # Twitch verification challenge
    if "challenge" in data:
        return data["challenge"], 200

    if request.headers.get("Twitch-Eventsub-Message-Type") == "notification":
        event = data.get("event", {})

        print("EventSub event received:")
        print(json.dumps(event, indent=2))

        reward_title = event.get("reward", {}).get("title", "")
        username = event.get("user_name", "").lower()

        if reward_title == "Add Camera Filter":
            print("📸 Camera Filter redeemed!")

            Thread(
                target=run_camera_filter,
                daemon=True,
            ).start()

        elif reward_title == "Rip a Vintage Pokemon Card":
            print(f"🎴 Pokémon card redeemed by {username}!")

            Thread(
                target=catch_pokemon,
                args=(username,),
                daemon=True,
            ).start()

        elif reward_title == "Start":
            print("🎥 Start Archiving redeemed!")
            start_archive_thread()

        elif reward_title == "Stop":
            print("🛑 Stop Archiving redeemed!")
            stop_archive()

    return jsonify({"message": "Event received"}), 200


# =============================
# SUBSCRIBE TO EVENTSUB
# =============================

def subscribe_to_channel_points():
    url = "https://api.twitch.tv/helix/eventsub/subscriptions"

    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {TWITCH_OAUTH_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "type": "channel.channel_points_custom_reward_redemption.add",
        "version": "1",
        "condition": {
            "broadcaster_user_id": BROADCASTER_USER_ID,
        },
        "transport": {
            "method": "webhook",
            "callback": WEBHOOK_URL,
            "secret": SECRET,
        },
    }

    print("Sending EventSub subscription request...")

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=15,
        )

        if response.status_code in (200, 202):
            print("✅ EventSub subscription successful!")
        else:
            print("❌ EventSub subscription failed:")
            print(response.status_code)
            print(response.text)

    except requests.RequestException as exc:
        print(f"❌ EventSub request error: {exc}")


# =============================
# MAIN
# =============================

if __name__ == "__main__":
    print("Starting Production Center server...")

    subscribe_to_channel_points()

    try:
        app.run(
            host="0.0.0.0",
            port=5000,
            debug=False,
            use_reloader=False,
        )

    finally:
        stop_archive()

