import os
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
CLIENT_SECRET = os.getenv("SECRET")

GAME_ID = "18122"


def get_app_token():
    response = requests.post(
        "https://id.twitch.tv/oauth2/token",
        params={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "client_credentials"
        }
    )

    response.raise_for_status()
    return response.json()["access_token"]


def get_top_wow_clips(token):
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(hours=200)

    response = requests.get(
        "https://api.twitch.tv/helix/clips",
        headers={
            "Client-ID": CLIENT_ID,
            "Authorization": f"Bearer {token}"
        },
        params={
            "game_id": GAME_ID,
            "started_at": yesterday.isoformat().replace("+00:00", "Z"),
            "ended_at": now.isoformat().replace("+00:00", "Z"),
            "first": 10
        }
    )

    response.raise_for_status()
    return response.json()["data"]


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