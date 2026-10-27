
from google import genai
from google.genai import types

import os
from pathlib import Path

from dotenv import load_dotenv

# Benito shares the Production Center's .env at the repo root.
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")
API_KEY = os.environ.get("GEMINI_API_KEY", "")
if not API_KEY:
    raise RuntimeError("Add GEMINI_API_KEY to the Production Center's .env file.")
client = genai.Client(api_key=API_KEY)

response = client.models.generate_content(
    model="gemini-3.6-flash",
    contents="Reply with exactly: Benito is here.",
)

print("Response object:", response)
print("Text:", repr(response.text))
print("Finish reason:", response.candidates[0].finish_reason if response.candidates else "No candidates")
