import json
import random
import time
from pathlib import Path
import os

import obsws_python as obs

from dotenv import load_dotenv



# =========================
# CONFIG
# =========================

CARD_FOLDER = Path(r"C:\Users\tyler\Downloads\PokemonCards")
COLLECTION_FILE = Path(
    r"C:\Users\tyler\Desktop\ProductionCenter2.0\pokemon_catches.json"
)

TOTAL_POKEMON = 151

load_dotenv()

OBS_HOST = os.getenv("OBS_HOST")
OBS_PORT = int(os.getenv("OBS_PORT"))
OBS_PASSWORD = os.getenv("OBS_PASSWORD")

SCENE_NAME = "MAIN"
SCENE_ITEM_ID = 21
OBS_SOURCE_NAME = "PokemonCard"
TEXT_SOURCE_NAME = "Collector"

DISPLAY_SECONDS = 10


# =========================
# COLLECTION
# =========================

def load_collections():
    if not COLLECTION_FILE.exists():
        return {}

    with open(COLLECTION_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_collections(collections):
    with open(COLLECTION_FILE, "w", encoding="utf-8") as f:
        json.dump(collections, f, indent=4)


# =========================
# OBS
# =========================

def update_collector_text(client, username, card_number, progress):
    text = (
        f"{username} caught Pokémon #{card_number}!\n"
        f"Collection: {progress}/151"
    )

    client.set_input_settings(
        TEXT_SOURCE_NAME,
        {
            "text": text
        },
        True
    )


def clear_collector_text(client):
    client.set_input_settings(
        TEXT_SOURCE_NAME,
        {
            "text": ""
        },
        True
    )


def display_card(card_number, username, progress):
    card_path = CARD_FOLDER / f"{card_number:03d}.png"

    if not card_path.exists():
        print(f"ERROR: Card does not exist: {card_path}")
        return False

    try:
        client = obs.ReqClient(
            host=OBS_HOST,
            port=OBS_PORT,
            password=OBS_PASSWORD
        )

        # Change the image
        client.set_input_settings(
            OBS_SOURCE_NAME,
            {
                "file": str(card_path)
            },
            True
        )

        # Update collector text
        update_collector_text(
            client,
            username,
            card_number,
            progress
        )

        # Starting and ending positions
        start_x = 1920
        final_x = 1148.5
        final_y = 268.0

        # Show the scene item
        client.send(
            "SetSceneItemEnabled",
            {
                "sceneName": SCENE_NAME,
                "sceneItemId": SCENE_ITEM_ID,
                "sceneItemEnabled": True
            }
        )

        # Start off-screen
        client.send(
            "SetSceneItemTransform",
            {
                "sceneName": SCENE_NAME,
                "sceneItemId": SCENE_ITEM_ID,
                "sceneItemTransform": {
                    "positionX": start_x,
                    "positionY": final_y
                }
            }
        )

        # Slide in
        steps = 30
        duration = 0.6
        step_time = duration / steps

        for i in range(steps + 1):
            progress_value = i / steps

            # Smooth ease-out
            eased = 1 - (1 - progress_value) ** 3

            x = start_x + (final_x - start_x) * eased

            client.send(
                "SetSceneItemTransform",
                {
                    "sceneName": SCENE_NAME,
                    "sceneItemId": SCENE_ITEM_ID,
                    "sceneItemTransform": {
                        "positionX": x,
                        "positionY": final_y
                    }
                }
            )

            time.sleep(step_time)

        print(f"Displayed card {card_number}")

        # Stay visible
        time.sleep(DISPLAY_SECONDS)

        # Slide back out
        for i in range(steps + 1):
            progress_value = i / steps

            # Smooth ease-in
            eased = progress_value ** 3

            x = final_x + (start_x - final_x) * eased

            client.send(
                "SetSceneItemTransform",
                {
                    "sceneName": SCENE_NAME,
                    "sceneItemId": SCENE_ITEM_ID,
                    "sceneItemTransform": {
                        "positionX": x,
                        "positionY": final_y
                    }
                }
            )

            time.sleep(step_time)

        # Hide card completely
        client.send(
            "SetSceneItemEnabled",
            {
                "sceneName": SCENE_NAME,
                "sceneItemId": SCENE_ITEM_ID,
                "sceneItemEnabled": False
            }
        )

        # Clear collector text
        clear_collector_text(client)

        print("Pokemon card hidden.")

        client.disconnect()

        return True

    except Exception as e:
        print(f"OBS ERROR: {e}")
        return False


# =========================
# CATCH LOGIC
# =========================

def catch_pokemon(username):
    username = username.lower()

    collections = load_collections()

    if username not in collections:
        collections[username] = []

    caught = set(collections[username])

    # Already completed the collection
    if len(caught) >= TOTAL_POKEMON:
        print(f"{username} already caught all 151!")
        return None

    # Only choose cards this user hasn't caught
    available = [
        number
        for number in range(1, TOTAL_POKEMON + 1)
        if number not in caught
    ]

    card_number = random.choice(available)

    # Save the catch
    collections[username].append(card_number)
    save_collections(collections)

    progress = len(collections[username])

    print(
        f"{username} caught card #{card_number} "
        f"({progress}/151)"
    )

    # Display it on stream
    display_card(
        card_number,
        username,
        progress
    )

    # Completion check
    if progress == TOTAL_POKEMON:
        print(f"🎉 {username} CAUGHT ALL 151!")

    return card_number


# =========================
# TEST
# =========================

