import os
from pathlib import Path

import obsws_python as obs
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

OBS_HOST = "192.168.1.184"
OBS_PORT = 4455
OBS_PASSWORD = os.getenv("OBS_PASSWORD")

SCENE_NAME = "MAIN"

client = obs.ReqClient(
    host=OBS_HOST,
    port=OBS_PORT,
    password=OBS_PASSWORD
)

response = client.get_scene_item_list(SCENE_NAME)

print(f"\nScene Items in '{SCENE_NAME}':\n")

for item in response.scene_items:
    print(f"Source Name: {item['sourceName']}")
    print(f"Scene Item ID: {item['sceneItemId']}")
    print("-" * 40)

client.disconnect()
