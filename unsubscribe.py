import requests
import json
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Your Twitch app credentials
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_OAUTH_TOKEN = os.getenv("TWITCH_OAUTH_TOKEN")

# Twitch API endpoint
EVENTSUB_URL = "https://api.twitch.tv/helix/eventsub/subscriptions"

def get_subscriptions():
    """Fetch all current EventSub subscriptions."""
    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {TWITCH_OAUTH_TOKEN}"
    }
    
    response = requests.get(EVENTSUB_URL, headers=headers)
    if response.status_code == 200:
        return response.json().get("data", [])
    else:
        print(f"Failed to fetch subscriptions: {response.text}")
        return []

def unsubscribe(subscription_id):
    """Delete a specific subscription by ID."""
    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {TWITCH_OAUTH_TOKEN}"
    }
    
    response = requests.delete(f"{EVENTSUB_URL}?id={subscription_id}", headers=headers)
    if response.status_code == 204:
        print(f"Unsubscribed from {subscription_id}")
    else:
        print(f"Failed to unsubscribe {subscription_id}: {response.text}")

def unsubscribe_all():
    """Fetch and remove all EventSub subscriptions."""
    subscriptions = get_subscriptions()
    if not subscriptions:
        print("No active subscriptions found.")
        return
    
    for sub in subscriptions:
        unsubscribe(sub["id"])

# Run the unsubscribe process
unsubscribe_all()