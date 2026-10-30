import os

import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Your Twitch app credentials. This must be the same user token Server.py uses.
# An app access token cannot list WebSocket subscriptions.
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_OAUTH_TOKEN = os.getenv("TWITCH_OAUTH_TOKEN")

# Twitch API endpoint. WebSocket and old webhook subscriptions are both listed here.
EVENTSUB_URL = "https://api.twitch.tv/helix/eventsub/subscriptions"


def describe(subscription):
    """One short line: event type, how it is delivered, and its id."""

    transport = subscription.get("transport") or {}
    method = transport.get("method") or "unknown"
    return (
        f"{subscription.get('type')} via {method}"
        f" ({subscription.get('status')}) {subscription.get('id')}"
    )


def get_subscriptions():
    """Fetch all current EventSub subscriptions."""
    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {TWITCH_OAUTH_TOKEN}",
    }

    response = requests.get(EVENTSUB_URL, headers=headers, timeout=15)
    if response.status_code == 200:
        return response.json().get("data", [])
    print(f"Failed to fetch subscriptions: {response.text}")
    return []


def unsubscribe(subscription_id):
    """Delete a specific subscription by ID."""
    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {TWITCH_OAUTH_TOKEN}",
    }

    response = requests.delete(
        f"{EVENTSUB_URL}?id={subscription_id}",
        headers=headers,
        timeout=15,
    )
    if response.status_code == 204:
        print(f"Unsubscribed from {subscription_id}")
    else:
        print(f"Failed to unsubscribe {subscription_id}: {response.text}")


def unsubscribe_all():
    """Delete every EventSub subscription on this token.

    WebSocket subscriptions and leftover webhook subscriptions are both
    removed by id. Run this once after you stop using a public callback
    so Twitch forgets that old address. A running server's WebSocket
    subscriptions also end when that server disconnects.
    """

    subscriptions = get_subscriptions()
    if not subscriptions:
        print("No active subscriptions found.")
        return

    for sub in subscriptions:
        print(f"Removing {describe(sub)}")
        unsubscribe(sub["id"])


if __name__ == "__main__":
    unsubscribe_all()
