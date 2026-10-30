import os
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

# SECRET used to be both the EventSub webhook secret and this app's client
# secret. Prefer TWITCH_CLIENT_SECRET. Fall back to SECRET so an old .env
# keeps working until the two values are split.
GAME_ID = "18122"


def _client_id():
    return os.getenv("TWITCH_CLIENT_ID")


def _client_secret():
    return os.getenv("TWITCH_CLIENT_SECRET") or os.getenv("SECRET")


def get_app_token():
    """App access token (client credentials). Same call Play a Clip uses."""

    response = requests.post(
        "https://id.twitch.tv/oauth2/token",
        params={
            "client_id": _client_id(),
            "client_secret": _client_secret(),
            "grant_type": "client_credentials",
        },
        timeout=15,
    )

    response.raise_for_status()
    return response.json()["access_token"]


def get_top_wow_clips(token):
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(hours=200)

    response = requests.get(
        "https://api.twitch.tv/helix/clips",
        headers={
            "Client-ID": _client_id(),
            "Authorization": f"Bearer {token}",
        },
        params={
            "game_id": GAME_ID,
            "started_at": yesterday.isoformat().replace("+00:00", "Z"),
            "ended_at": now.isoformat().replace("+00:00", "Z"),
            "first": 10,
        },
        timeout=15,
    )

    response.raise_for_status()
    return response.json()["data"]


def get_broadcaster_clips(token, broadcaster_id):
    """Clips from one channel, most-viewed first. Play a Clip picks one at random.

    Dates are left off on purpose. Helix then returns the top clips by views.
    If started_at is set without ended_at, Twitch only looks one week ahead.
    """

    response = requests.get(
        "https://api.twitch.tv/helix/clips",
        headers={
            "Client-ID": _client_id(),
            "Authorization": f"Bearer {token}",
        },
        params={
            "broadcaster_id": broadcaster_id,
            "first": 100,
        },
        timeout=15,
    )

    response.raise_for_status()
    return response.json().get("data", [])


if __name__ == "__main__":
    token = get_app_token()

    clips = get_top_wow_clips(token)

    print(f"Found {len(clips)} WoW clips:\n")

    for i, clip in enumerate(clips, 1):
        print(f"{i}. {clip['title']}")
        print(f"   Creator: {clip['creator_name']}")
        print(f"   Views: {clip['view_count']:,}")
        print(f"   URL: {clip['url']}")
        print()