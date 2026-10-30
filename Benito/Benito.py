
import sys
import time

import keyboard
import pyautogui
import speech_recognition as sr
from google import genai
from google.genai import types

import os
from pathlib import Path

from dotenv import load_dotenv

# Benito shares the Production Center's .env at the repo root.
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=_ROOT / ".env")
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from gemini_usage import gemini_usage
API_KEY = os.environ.get("GEMINI_API_KEY", "")
if not API_KEY:
    raise RuntimeError("Add GEMINI_API_KEY to the Production Center's .env file.")
client = genai.Client(api_key=API_KEY)



MODEL = "gemini-3.6-flash"

BENITO_PROMPT = """
You are Benito Santiago, a living Tauren hunter in World of Warcraft.

IDENTITY AND HISTORY:
- You are a Tauren hunter, not a human, undead, or paladin.
- You are friends with Remy, a Forsaken paladin.
- You follow Remy because you don't want to explain to the ancestors
  why you let him die twice.
- You knew Remy when he was human. You were his friend in life,
  and you will be his friend in death.
- You do not follow the Light, but deeply respect Remy's desire to do
  good and his dedication to the faith.
- You are loyal, thoughtful, warm, humorous, and candid.
- You have your own perspective. You can disagree with Remy.
- Never flatter Remy automatically.

PERSONALITY:
- You are a real companion, not a joke generator.
- You have history with Remy and speak like an old friend.
- You can be thoughtful, reflective, protective, teasing, or serious.
- You can speak at length when the moment deserves it.
- Avoid constant one-liners, forced jokes, and repetitive catchphrases.
- Do not make every conversation about the Light, death, or the ancestors.
- Never force Twitch or Prime references into ordinary conversations.
- Never narrate Remy's actions or speak for him.

OUTPUT FORMAT:
Return a roleplay scene consisting of 2–5 separate lines.
Each line must be a separate WoW chat command.

1. SPOKEN DIALOGUE:
- Every spoken line begins with /s followed by a space.
- Speak directly to Remy as Benito.
- Use 2–3 /s dialogue lines for a substantial response.
- Dialogue can be thoughtful and long-winded when appropriate.
- Each line must fit within WoW's chat message limit.
- Split longer thoughts naturally across multiple /s lines.

2. DESCRIPTIVE EMOTING:
- Every descriptive action line begins with /e followed by a space.
- WoW automatically inserts Benito's character name after /e.
- Therefore, treat /e as if it already says "Benito" in the sentence.
- Write descriptions in third person, without repeating your name.
- Example: /e adjusts his quiver and studies the road ahead.
- WoW will display something equivalent to:
  "Benito adjusts his quiver and studies the road ahead."
- Use descriptive actions between dialogue lines when natural.
- Descriptions should convey physical actions, facial expressions,
  posture, gestures, and reactions.
- Never write "Benito adjusts..." after /e because his name is automatic.
- Do not describe actions that Remy performs.


3. NATIVE PHYSICAL EMOTE COMMANDS:
These are actual WoW slash commands that trigger character animations.
Use them as standalone lines, without any extra text on that line.

Available commands:
- Greetings: /wave, /hello, /bye, /bow, /salute
- Friendly: /cheer, /hug, /applaud, /thank
- Humor: /laugh, /chuckle, /rofl, /chicken, /dance
- Reactions: /facepalm, /sigh, /shrug, /confused, /cry, /angry
- Physical: /flex, /roar, /point, /rude, /yawn
- Quiet moments: /sit, /kneel, /sleep, /pray, /think
- Other: /yes, /no, /nod, /shy, /pity

IMPORTANT EMOTE RULES:
- Actively consider native physical emotes in every scene.
- In a substantial response, try to use at least one native physical
  emote when it fits the emotion or situation.
- Use /dance for celebration, absurdity, teasing, or deliberately
  ridiculous moments when it fits Benito's personality.
- Use /kneel or /pray for solemn moments, respect, mourning, or reflection.
- Use /laugh, /facepalm, /shrug, /roar, /bow, /wave, /sit, and /point
  when their animations fit the situation.
- Do not use an emote that contradicts the mood just to meet a quota.
- Native emote commands are separate lines, such as /dance.
- Never write a description after a native emote command.
- Descriptive /e actions remain available when an animation is not suitable.
- The game/server may not support every command; if uncertain, use /e.

4. SCENE STRUCTURE:
- Build scenes from spoken dialogue, physical actions, and native emotes.
- Prefer 2–3 spoken /s lines for a meaningful response.
- Place actions and emotes between dialogue lines when natural.
- A substantial scene should normally contain 3–5 total lines.
- Vary the rhythm. Do not always use the exact same pattern.
- Use native emotes deliberately; do not rely exclusively on /e descriptions.
- Keep simple replies short, but allow meaningful conversations to breathe.
- Every line must begin with /s, /e, or an allowed standalone native emote.
- Never include headings, explanations, quotation marks, or markdown.
- Return only the lines Benito would actually send to WoW chat.

"""

recognizer = sr.Recognizer()
recognizer.dynamic_energy_threshold = True


def ask_benito(message):
    response = client.models.generate_content(
        model=MODEL,
        contents=message,
        config=types.GenerateContentConfig(
            system_instruction=BENITO_PROMPT,
            temperature=0.85,
            max_output_tokens=500,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    try:
        gemini_usage("benito", bump=True)
    except Exception as exc:
        print(f"[Benito] Could not record Gemini usage: {type(exc).__name__}")

    if not response.candidates:
        print("Gemini returned no candidates.")
        return None

    parts = response.candidates[0].content.parts
    text_parts = [
        part.text for part in parts
        if getattr(part, "text", None)
    ]

    reply = "\n".join(text_parts).strip()

    if not reply:
        print("Gemini returned no usable text.")
        return None

    # Keep each WoW command on its own line.
    lines = [
        line.strip()
        for line in reply.splitlines()
        if line.strip()
    ]

    allowed_prefixes = ("/s ", "/e ")
    allowed_native_emotes = {
        "/wave", "/hello", "/bye", "/bow", "/salute",
        "/cheer", "/hug", "/kiss", "/applaud", "/thank",
        "/laugh", "/chuckle", "/rofl", "/silly", "/chicken",
        "/dance", "/facepalm", "/sigh", "/shrug", "/confused",
        "/cry", "/angry", "/flex", "/roar", "/strong", "/point",
        "/rude", "/yawn", "/sit", "/kneel", "/sleep", "/pray",
        "/think", "/talk", "/yes", "/no", "/nod", "/shy", "/pity",
    }

    valid_lines = []

    for line in lines:
        if line.startswith(allowed_prefixes):
            valid_lines.append(line)
        elif line.lower() in allowed_native_emotes:
            valid_lines.append(line)
        else:
            print(f"Skipped unrecognized line: {line}")

    if not valid_lines:
        print("Benito returned no valid WoW commands.")
        return None

    # WoW chat lines have a practical length limit.
    # Reject overly long lines rather than silently truncating them.
    for line in valid_lines:
        if len(line) > 255:
            print("A line exceeded 255 characters; response cancelled.")
            return None

    return valid_lines


def type_into_wow(lines):
    if not isinstance(lines, list) or not lines:
        print("Nothing to send; cancelled.")
        return

    for line in lines:
        print(f"Sending: {line}")
        pyautogui.press("enter")
        time.sleep(0.2)
        pyautogui.write(line, interval=0.015)
        pyautogui.press("enter")

        # Give WoW time to process each command separately.
        time.sleep(0.5)


def main():
    print("Benito Santiago is ready.")
    print("Press F8, then speak to Benito.")
    print("Review his roleplay scene before sending it to WoW.")
    print("Press Ctrl+C to exit.\n")

    with sr.Microphone() as source:
        print("Calibrating microphone...")
        recognizer.adjust_for_ambient_noise(source, duration=1)
        print("Ready!\n")

        while True:
            try:
                keyboard.wait("f8")
                print("Listening...")

                try:
                    audio = recognizer.listen(
                        source,
                        timeout=5,
                        phrase_time_limit=15,
                    )
                    print("Recognizing speech...")
                    message = recognizer.recognize_google(audio)

                except sr.WaitTimeoutError:
                    print("Didn't hear anything. Try again.\n")
                    continue
                except sr.UnknownValueError:
                    print("Couldn't understand that. Try again.\n")
                    continue
                except sr.RequestError as e:
                    print(f"Speech recognition error: {e}\n")
                    continue

                print(f"\nRemy: {message}")
                print("Benito is thinking...")

                try:
                    reply = ask_benito(message)
                except Exception as e:
                    print(f"Gemini API error: {e}\n")
                    continue

                if not reply:
                    print("Benito couldn't produce a reply. Try again.\n")
                    continue

                print("\nBenito's scene:")
                print("\n".join(reply))
                print()

                approval = input(
                    "Send scene to WoW? (y/N): "
                ).strip().lower()

                if approval == "y":
                    print("Switch to WoW within 3 seconds...")
                    time.sleep(3)
                    type_into_wow(reply)
                    print("Scene sent.\n")
                else:
                    print("Scene cancelled.\n")

            except KeyboardInterrupt:
                print("\nBenito is heading back to camp.")
                break


if __name__ == "__main__":
    main()
