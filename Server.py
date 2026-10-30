import asyncio
import hashlib
import hmac
import ipaddress
import json
import os
import random
import re
import sys
import time
import subprocess
import threading
from collections import OrderedDict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Thread
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from flask import Flask, Response, abort, jsonify, request, send_file, send_from_directory

import clips
from gemini_usage import gemini_usage
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

ARCHIVE_SCRIPT = BASE_DIR / "archive.py"
CREDITS_FILE = BASE_DIR / "stream_credits.json"
BANNED_WORDS_FILE = BASE_DIR / "banned_words.txt"
VOICE_LINES_DIR = BASE_DIR / "voice_lines"
CREDITS_PAGE = BASE_DIR / "credits.html"

# EventSub signatures use EVENTSUB_SECRET. Older .env files only have SECRET,
# which was also the Twitch client secret in clips.py. Fall back so those
# files keep verifying. Set both names when you can split the two jobs.
def get_eventsub_secret():
    return os.getenv("EVENTSUB_SECRET") or os.getenv("SECRET") or ""


def clip_reward_title():
    return (os.getenv("CLIP_REWARD_TITLE") or "Play a Clip").strip()


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
# WIDGET EVENT FEED
# =============================

EVENTS = deque(maxlen=200)
EVENT_ID = 0
EVENTS_LOCK = threading.Lock()


def publish(etype, **fields):
    """Append one event for widgets polling GET /events."""

    global EVENT_ID
    with EVENTS_LOCK:
        EVENT_ID += 1
        EVENTS.append({
            "id": EVENT_ID,
            "type": etype,
            "ts": time.time(),
            **fields,
        })


@app.route("/events")
def events():
    since = request.args.get("since", default=0, type=int)
    if since is None:
        since = 0
    with EVENTS_LOCK:
        out = [event for event in EVENTS if event["id"] > since]
        last = EVENT_ID
    resp = jsonify({"last_id": last, "events": out})
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Cache-Control"] = "no-store"
    return resp


# =============================
# END CREDITS
# =============================

CREDIT_GROUPS = ("subs", "gifts", "bits", "follows")
CREDITS_LOCK = threading.Lock()


def empty_credits():
    return {group: [] for group in CREDIT_GROUPS}


def load_credits():
    """Read the roll. Caller holds CREDITS_LOCK. A bad file starts fresh."""

    data = empty_credits()
    if not CREDITS_FILE.is_file():
        return data
    try:
        loaded = json.loads(CREDITS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print("[Server] WARNING: credits file was unreadable. Starting a fresh roll.")
        return empty_credits()
    if not isinstance(loaded, dict):
        return empty_credits()
    for group in CREDIT_GROUPS:
        entries = loaded.get(group)
        if isinstance(entries, list):
            data[group] = entries
    return data


def save_credits(data):
    """Write the roll. Caller holds CREDITS_LOCK."""

    CREDITS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = CREDITS_FILE.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temporary, CREDITS_FILE)


def add_credit(group, user, login, amount=None):
    """Remember a viewer once per group. Bits and gift counts add up."""

    if group not in CREDIT_GROUPS:
        return

    shown = (user or "").strip() or "Anonymous"
    login = (login or "").strip()
    key = login.lower() if login else shown.lower()
    try:
        extra = int(amount) if amount else 0
    except (TypeError, ValueError):
        extra = 0
    if extra < 0:
        extra = 0

    with CREDITS_LOCK:
        data = load_credits()
        entries = data.setdefault(group, [])
        for entry in entries:
            entry_login = (entry.get("login") or "").lower()
            entry_key = entry_login if entry_login else (entry.get("user") or "").lower()
            if entry_key != key:
                continue
            if extra:
                entry["amount"] = int(entry.get("amount") or 0) + extra
                save_credits(data)
            return
        new_entry = {"user": shown, "login": login}
        if extra:
            new_entry["amount"] = extra
        entries.append(new_entry)
        save_credits(data)


def reset_credits():
    with CREDITS_LOCK:
        save_credits(empty_credits())


def credits_for_display():
    """Names grouped the way the credits page prints them."""

    with CREDITS_LOCK:
        data = load_credits()

    lines = {
        "Subs": [],
        "Gifted Subs": [],
        "Bits": [],
        "Follows": [],
    }
    for entry in data.get("subs", []):
        lines["Subs"].append(entry.get("user") or "Anonymous")
    for entry in data.get("gifts", []):
        name = entry.get("user") or "Anonymous"
        amount = int(entry.get("amount") or 0)
        if amount:
            word = "sub" if amount == 1 else "subs"
            lines["Gifted Subs"].append(f"{name} — {amount} {word}")
        else:
            lines["Gifted Subs"].append(name)
    for entry in data.get("bits", []):
        name = entry.get("user") or "Anonymous"
        amount = int(entry.get("amount") or 0)
        if amount:
            lines["Bits"].append(f"{name} — {amount:,} bits")
        else:
            lines["Bits"].append(name)
    for entry in data.get("follows", []):
        lines["Follows"].append(entry.get("user") or "Anonymous")
    return lines


@app.route("/credits.json")
def credits_json():
    resp = jsonify(credits_for_display())
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/credits")
def credits_page():
    return send_file(CREDITS_PAGE)


@app.route("/credits/reset", methods=["POST"])
def credits_reset():
    reset_credits()
    return jsonify({"ok": True})


def viewer_name(event):
    """Display name and login. Anonymous gifts and cheers have neither."""

    if event.get("is_anonymous") or not (event.get("user_name") or event.get("user_login")):
        return "Anonymous", ""
    return event.get("user_name") or "", event.get("user_login") or ""


# =============================
# WORD FILTER
# =============================

# Empty or missing banned_words.txt filters nothing (fail open).
_banned_cache = {"mtime": None, "words": ()}


def banned_words():
    try:
        mtime = BANNED_WORDS_FILE.stat().st_mtime if BANNED_WORDS_FILE.is_file() else None
    except OSError:
        return ()
    if mtime == _banned_cache["mtime"]:
        return _banned_cache["words"]

    words = []
    if mtime is not None:
        try:
            lines = BANNED_WORDS_FILE.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            print(f"[Server] WARNING: could not read banned words: {exc}")
            return ()
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            words.append(line)
    words.sort(key=len, reverse=True)
    _banned_cache["mtime"] = mtime
    _banned_cache["words"] = tuple(words)
    return _banned_cache["words"]


def censor_viewer_text(text):
    """Star out whole words listed in banned_words.txt. Usernames are not filtered."""

    if not text:
        return text or ""
    words = banned_words()
    if not words:
        return text
    cleaned = text
    for word in words:
        pattern = re.compile(rf"\b{re.escape(word)}\b", re.IGNORECASE)
        cleaned = pattern.sub(lambda match: "*" * len(match.group(0)), cleaned)
    return cleaned


# =============================
# VOICE LINES AND PLAY A CLIP
# =============================

_last_voice_line = None
_voice_lock = threading.Lock()


def pick_voice_line(character="orc"):
    """Random mp3/wav. With 2 or more files, do not repeat the last pick."""

    global _last_voice_line
    folder = VOICE_LINES_DIR / character
    if not folder.is_dir():
        return ""
    files = sorted(
        path.name
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in {".mp3", ".wav"}
    )
    if not files:
        return ""
    with _voice_lock:
        choices = files
        if len(files) >= 2 and _last_voice_line in files:
            choices = [name for name in files if name != _last_voice_line]
        pick = random.choice(choices)
        _last_voice_line = pick
    return f"/voice_lines/{character}/{quote(pick)}"


def fetch_random_clip():
    """One random clip from this channel, using the app token in clips.py."""

    broadcaster_id = os.getenv("BROADCASTER_USER_ID")
    if not broadcaster_id:
        raise RuntimeError("BROADCASTER_USER_ID is not set")
    token = clips.get_app_token()
    found = clips.get_broadcaster_clips(token, broadcaster_id)
    if not found:
        return None
    return random.choice(found)


def play_clip_for(user, login, reward=""):
    """Fetch a clip and a voice line, then publish a clip event either way."""

    clip = None
    try:
        clip = fetch_random_clip()
    except Exception as exc:
        # Do not print the exception text. A token failure can include the URL.
        print(f"[Server] WARNING: could not fetch a clip ({type(exc).__name__}).")
    if not clip:
        print("[Server] WARNING: no clip available. Publishing empty clip fields.")
        clip = {}

    voice_line = pick_voice_line("orc")
    if not voice_line:
        print("[Server] WARNING: no voice lines in voice_lines/orc/. Publishing an empty voice_line.")

    duration = clip.get("duration")
    if duration is None:
        duration = 0

    publish(
        "clip",
        user=user or "",
        login=login or "",
        clip_id=clip.get("id") or "",
        clip_url=clip.get("url") or "",
        embed_url=clip.get("embed_url") or "",
        title=clip.get("title") or "",
        creator=clip.get("creator_name") or "",
        duration=duration,
        thumbnail_url=clip.get("thumbnail_url") or "",
        voice_line=voice_line or "",
        reward=reward or "",
    )


def _voice_line_path(name, filename):
    """Resolve a file inside voice_lines/<name>/, or None if it is not safe."""

    if not name or not filename:
        return None
    if name in {".", ".."} or filename in {".", ".."}:
        return None
    if "/" in name or "\\" in name or "/" in filename or "\\" in filename:
        return None
    root = VOICE_LINES_DIR.resolve()
    folder = (root / name).resolve()
    path = (folder / filename).resolve()
    if not folder.is_relative_to(root) or folder == root:
        return None
    if not path.is_relative_to(folder):
        return None
    if path.suffix.lower() not in {".mp3", ".wav"}:
        return None
    if not path.is_file():
        return None
    return path


@app.route("/voice_lines/<name>/<filename>")
def serve_voice_line(name, filename):
    path = _voice_line_path(name, filename)
    if path is None:
        abort(404)
    mimetype = "audio/wav" if path.suffix.lower() == ".wav" else "audio/mpeg"
    return send_file(path, mimetype=mimetype)


def widgets_directory():
    """WIDGETS_DIR from .env. A relative path is inside this project, not a fixed drive."""

    raw = (os.getenv("WIDGETS_DIR") or "").strip()
    if not raw:
        return None
    folder = Path(raw)
    if not folder.is_absolute():
        folder = BASE_DIR / folder
    return folder


@app.route("/widgets/<path:p>")
def widgets(p):
    """Serve one widget file. Twitch clip embeds will not play from file://."""

    folder = widgets_directory()
    if folder is None:
        print("[Server] WIDGETS_DIR is not set. Add it to .env to serve /widgets/.")
        abort(404)
    if not folder.is_dir():
        print(f"[Server] WIDGETS_DIR is missing or not a folder: {folder}")
        abort(404)
    # send_from_directory rejects .. so a URL cannot escape this folder.
    response = send_from_directory(folder, p)
    response.headers["Cache-Control"] = "no-store"
    return response


# =============================
# TEXT TO SPEECH
# =============================

TTS_DIR = BASE_DIR / "tts_cache"
TTS_VOICES = {
    "en-US-AnaNeural",
    "en-US-JennyNeural",
    "en-US-AriaNeural",
    "en-GB-MaisieNeural",
    "en-US-AshleyNeural",
    "en-GB-SoniaNeural",
    "en-AU-NatashaNeural",
    "es-MX-DaliaNeural",
    "pt-BR-FranciscaNeural",
    "fr-FR-DeniseNeural",
    "ja-JP-NanamiNeural",
    "ko-KR-SunHiNeural",
    "zh-CN-XiaoxiaoNeural",
    "zh-TW-HsiaoChenNeural",
    "de-DE-KatjaNeural",
    "nl-NL-ColetteNeural",
    "en-HK-SamNeural",
}
TTS_DEFAULT = "en-US-AriaNeural"
TTS_MAX = 300


def _edge_tts_bytes(text, voice, rate, pitch):
    import edge_tts

    async def run():
        out = bytearray()
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                out += chunk["data"]
        return bytes(out)

    return asyncio.run(run())


def _eleven_bytes(text):
    voice_id = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    response = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={
            "xi-api-key": os.environ["ELEVENLABS_API_KEY"],
            "accept": "audio/mpeg",
        },
        json={"text": text, "model_id": "eleven_turbo_v2_5"},
        timeout=20,
    )
    response.raise_for_status()
    return response.content


@app.route("/tts")
def tts():
    text = " ".join((request.args.get("text") or "").split())
    if not text:
        abort(400)
    if len(text) > TTS_MAX:
        abort(413)
    text = censor_viewer_text(text)

    voice = request.args.get("voice") or TTS_DEFAULT
    if voice not in TTS_VOICES:
        voice = TTS_DEFAULT
    rate = request.args.get("rate", "+0%")
    pitch = request.args.get("pitch", "+0Hz")
    rate_match = re.fullmatch(r"([+-])(\d{1,2})%", rate)
    rate = rate if rate_match and int(rate_match[2]) <= 50 else "+0%"
    pitch_match = re.fullmatch(r"([+-])(\d{1,2})Hz", pitch)
    pitch = pitch if pitch_match and int(pitch_match[2]) <= 60 else "+0Hz"

    engine = "eleven" if os.getenv("ELEVENLABS_API_KEY") and request.args.get("engine") == "eleven" else "edge"
    key = hashlib.sha1(f"{engine}|{voice}|{rate}|{pitch}|{text}".encode()).hexdigest()
    TTS_DIR.mkdir(parents=True, exist_ok=True)
    path = TTS_DIR / f"{key}.mp3"
    if not path.is_file():
        try:
            if engine == "eleven":
                data = _eleven_bytes(text)
            else:
                data = _edge_tts_bytes(text, voice, rate, pitch)
            if not data:
                raise RuntimeError("no audio")
        except Exception as exc:
            print(f"[Server] TTS failed: {exc}")
            abort(502)
        temporary = path.with_suffix(".mp3.tmp")
        temporary.write_bytes(data)
        os.replace(temporary, path)

    resp = Response(path.read_bytes(), mimetype="audio/mpeg")
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


# =============================
# TRANSLATE
# =============================

# Google's gtx client is unofficial. It can change or rate-limit without notice.
TR_MAX = 300
TR_CACHE = OrderedDict()
TR_CACHE_LOCK = threading.Lock()
TR_TARGETS = {
    "en": ("en", "EN-US"),
    "es": ("es", "ES"),
    "pt": ("pt", "PT-BR"),
    "pt-br": ("pt", "PT-BR"),
    "fr": ("fr", "FR"),
    "ja": ("ja", "JA"),
    "ko": ("ko", "KO"),
    "zh-hans": ("zh-CN", "ZH-HANS"),
    "zh-hant": ("zh-TW", "ZH-HANT"),
    "de": ("de", "DE"),
    "nl": ("nl", "NL"),
}


def _google(text, target, source):
    response = requests.get(
        "https://translate.googleapis.com/translate_a/single",
        timeout=6,
        params={
            "client": "gtx",
            "sl": source or "auto",
            "tl": target,
            "dt": "t",
            "q": text,
        },
    )
    response.raise_for_status()
    payload = response.json()
    translated = "".join(segment[0] for segment in payload[0] if segment and segment[0])
    if not translated:
        raise RuntimeError("empty google result")
    detected = payload[2] or source or ""
    return translated, str(detected).lower()


def _mymemory(text, target, source):
    response = requests.get(
        "https://api.mymemory.translated.net/get",
        timeout=6,
        params={"q": text, "langpair": f"{source or 'autodetect'}|{target}"},
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("responseStatus") != 200 or payload.get("quotaFinished"):
        raise RuntimeError(payload.get("responseDetails"))
    data = payload["responseData"]
    detected = data.get("detectedLanguage") or source or ""
    return data["translatedText"], str(detected).lower()


def _deepl(text, target, source):
    key = os.environ["DEEPL_API_KEY"]
    if key.endswith(":fx"):
        host = "https://api-free.deepl.com"
    else:
        host = "https://api.deepl.com"
    data = {"text": [text], "target_lang": target}
    if source:
        data["source_lang"] = source.split("-")[0].upper()
    response = requests.post(
        host + "/v2/translate",
        json=data,
        headers={"Authorization": "DeepL-Auth-Key " + key},
        timeout=6,
    )
    response.raise_for_status()
    translated = response.json()["translations"][0]
    detected = translated.get("detected_source_language", "")
    return translated["text"], str(detected).lower()


def _translate_uncached(text, target, source):
    google_target, deepl_target = TR_TARGETS[target]
    source_code = None
    if source:
        source_code = TR_TARGETS.get(source, (source, None))[0]

    engines = [
        lambda: _google(text, google_target, source_code),
        lambda: _mymemory(text, google_target, source_code),
    ]
    if os.getenv("DEEPL_API_KEY"):
        engines.append(lambda: _deepl(text, deepl_target, source))

    result = None
    detected = ""
    for engine in engines:
        try:
            result, detected = engine()
            break
        except Exception as exc:
            print(f"[Server] Translate engine failed: {exc}")
    if result is None:
        abort(502)

    detected = (detected or "").lower()
    return {
        "text": result,
        "source": source or detected,
        "target": target,
        "detected": detected,
    }


@app.route("/translate")
def translate():
    text = " ".join((request.args.get("text") or "").split())
    target = (request.args.get("target") or "").lower()
    source = (request.args.get("source") or "").lower() or None
    if not text or target not in TR_TARGETS:
        abort(400)
    if len(text) > TR_MAX:
        abort(413)
    text = censor_viewer_text(text)

    cache_key = f"{target}|{source}|{text}"
    with TR_CACHE_LOCK:
        cached = TR_CACHE.get(cache_key)
        if cached is not None:
            TR_CACHE.move_to_end(cache_key)
            out = cached
        else:
            out = None
    if out is None:
        out = _translate_uncached(text, target, source)
        with TR_CACHE_LOCK:
            TR_CACHE[cache_key] = out
            TR_CACHE.move_to_end(cache_key)
            while len(TR_CACHE) > 500:
                TR_CACHE.popitem(last=False)

    resp = jsonify(out)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Cache-Control"] = "no-store"
    return resp


# =============================
# ASK THE MONK
# =============================

# Same env name Benito already reads. Never print or return this value.
MONK_PROMPT = """You are Master Brewpaw, a warm, wise, and funny pandaren monk and brewmaster who gives counsel to viewers on
a World of Warcraft Twitch stream (channel: remyfriend). A viewer named {user} asks you a question.
Answer in 1-3 sentences, under 45 words total, in natural, fluent, modern English.
Be kind, playful, and genuinely helpful. Tea, brew, balance, and WoW metaphors are welcome; keep them light.
Never use broken or "accented" English, stereotypes, or fortune-cookie cliches like "Confucius say".
Keep it Twitch-safe: no profanity, sexual content, hate, or politics.
Do not give medical, legal, financial, or crisis advice. If the question touches self-harm, abuse, health,
or legal trouble, respond gently and encourage them to reach out to someone they trust or a professional or local
helpline. Never claim to be an AI; you are the monk. Do not repeat the question."""

MONK_SAYINGS = (
    "A cup poured in a hurry spills on the table. Slow down, and the answer will steep.",
    "Even the strongest brew starts as plain water and patience.",
    "When the path is foggy, take the next small step. The mist clears for walkers, not worriers.",
    "Balance is not standing still. It is a hundred tiny wobbles, corrected with a smile.",
    "Rest is part of the training. Bamboo grows in the quiet, too.",
    "If the load is too heavy, share it. Even a monk calls friends to carry the keg.",
    "You cannot pour from an empty kettle. Refill yourself first.",
    "Mistakes are just practice wearing a disguise.",
    "The loudest thought in your head is not always the wisest. Let it cool like tea.",
    "Laugh at your stumbles. The ground is a patient teacher.",
    "A wipe is only a lesson with a repair bill.",
    "Drink some water, stretch your paws, then decide. Most choices taste better after a sip.",
    "The best time to start was yesterday. The second best is after this cup.",
    "Do not compare your first brew to another monk's hundredth.",
    "Some days you are the tank, some days you are the floor. Both get back up.",
    "Be gentle with yourself. You are the only body you get to level.",
    "If you cannot decide, flip a coin. Your heart will tell you which side it hoped for.",
    "Kindness is a brew that never goes stale.",
    "Wisdom is knowing when to push, and knowing when to go make a snack.",
    "A good friend is like a good tavern: warm, loud, and always open.",
    "The mountain is climbed one ledge at a time, and with frequent tea breaks.",
    "Worry is a rocking chair. Lots of motion, no distance.",
    "Small habits are like small coins. Save enough and you can buy the epic mount.",
    "Ask for help early. Pride has never once rezzed anyone.",
    "A clear mind is like still water. Stop stirring and you will see the bottom.",
    "Sleep on it. Tomorrow's you is better rested and slightly smarter.",
    "Every master was once a level one with no idea what the buttons did.",
    "Do one thing well, then the next. Even a brewmaster only stirs one keg at a time.",
    "When in doubt, be kind, drink water, and log off at a reasonable hour.",
    "The journey matters more than the loot. But the loot is nice, too.",
)

_counsel_last_ask = {}


def text_hits_banned_word(text):
    """True when banned_words.txt would change this text."""

    if not text:
        return False
    return censor_viewer_text(text) != text


def _counsel_int(name, default):
    try:
        return int(os.getenv(name) or default)
    except ValueError:
        return int(default)


def counsel_answer_json(answer, source):
    response = jsonify({"answer": answer, "source": source})
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Cache-Control"] = "no-store"
    return response


def canned_counsel():
    return counsel_answer_json(random.choice(MONK_SAYINGS), "canned")


def trim_counsel_answer(text, limit=300):
    """Keep about 300 characters, ending on a sentence when there is one."""

    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    window = text[:limit]
    for mark in (".", "!", "?"):
        index = window.rfind(mark)
        if index >= 40:
            return window[:index + 1].strip()
    return window.rstrip()


def counsel_over_cap():
    """True when the monk's own cap is hit, or the shared project day is nearly full."""

    mine, total = gemini_usage("monk")
    if mine >= _counsel_int("COUNSEL_DAILY_CAP", "100"):
        return True
    # Free-tier requests are per Google project, shared with Benito.
    # 900 leaves room under a typical 1,000-request day. Change it in .env.
    if total >= _counsel_int("GEMINI_PROJECT_DAILY_CAP", "900"):
        return True
    return False


@app.route("/counsel")
def counsel():
    question = (request.args.get("q") or "").strip()[:200]
    user = (request.args.get("user") or "friend")[:25]
    if not question or text_hits_banned_word(question):
        return canned_counsel()

    now = time.time()
    key = user.lower()
    if now - _counsel_last_ask.get(key, 0) < _counsel_int("COUNSEL_USER_COOLDOWN", "60"):
        return canned_counsel()

    if counsel_over_cap():
        return canned_counsel()

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return canned_counsel()

    _counsel_last_ask[key] = now
    model = os.getenv("COUNSEL_MODEL") or "gemini-2.5-flash-lite"
    try:
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": api_key},
            timeout=8,
            json={
                "system_instruction": {"parts": [{"text": MONK_PROMPT.format(user=user)}]},
                "contents": [{"role": "user", "parts": [{"text": question}]}],
                "generationConfig": {"maxOutputTokens": 120, "temperature": 0.9},
            },
        )
        response.raise_for_status()
        gemini_usage("monk", bump=True)
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        if not text or text_hits_banned_word(text):
            return canned_counsel()
        return counsel_answer_json(trim_counsel_answer(text), "gemini")
    except Exception as exc:
        print(f"[Server] Counsel failed: {type(exc).__name__}")
        return canned_counsel()


# =============================
# TUNNEL GUARD
# =============================

def _is_loopback(addr):
    if not addr:
        return False
    host = addr.strip().lower()
    if host.startswith("::ffff:"):
        host = host.split("::ffff:", 1)[1]
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _request_is_local():
    """True for OBS on this PC. False when ngrok forwarded the request."""

    if request.headers.get("X-Forwarded-For") or request.headers.get("X-Forwarded-Host"):
        return False
    return _is_loopback(request.remote_addr)


@app.before_request
def tunnel_guard():
    """ngrok exposes the whole port. Only POST /webhook is allowed from the internet."""

    if request.path == "/webhook" and request.method == "POST":
        return None
    if _request_is_local():
        return None
    return jsonify({"error": "local only"}), 403


# =============================
# EVENTSUB WEBHOOK
# =============================

MAX_EVENT_AGE = timedelta(minutes=10)
MAX_SEEN_MESSAGES = 1000
_seen_ids = deque()
_seen_set = set()
_seen_lock = threading.Lock()


def signature_matches(raw_body):
    """HMAC-SHA256 of message id + timestamp + raw body, compared in constant time."""

    secret = get_eventsub_secret()
    if not secret:
        return False
    message_id = request.headers.get("Twitch-Eventsub-Message-Id", "")
    timestamp = request.headers.get("Twitch-Eventsub-Message-Timestamp", "")
    signature = request.headers.get("Twitch-Eventsub-Message-Signature", "")
    if not isinstance(signature, str) or not signature:
        return False
    digest = hmac.new(
        secret.encode("utf-8"),
        message_id.encode("utf-8") + timestamp.encode("utf-8") + raw_body,
        hashlib.sha256,
    ).hexdigest()
    expected = "sha256=" + digest
    return hmac.compare_digest(expected, signature)


def parse_eventsub_timestamp(value):
    """Twitch sends RFC3339 with nanoseconds. Python 3.10 only accepts microseconds."""

    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    if "." in text:
        head, tail = text.split(".", 1)
        digits = []
        rest = ""
        for index, char in enumerate(tail):
            if char.isdigit():
                digits.append(char)
            else:
                rest = tail[index:]
                break
        fraction = "".join(digits[:6])
        text = f"{head}.{fraction}{rest}" if fraction else f"{head}{rest}"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def timestamp_is_stale(value):
    parsed = parse_eventsub_timestamp(value)
    if parsed is None:
        return True
    age = datetime.now(timezone.utc) - parsed
    return age > MAX_EVENT_AGE


def already_seen(message_id):
    """True the second time we see this id. The memory cap keeps the set small."""

    with _seen_lock:
        if message_id in _seen_set:
            return True
        _seen_ids.append(message_id)
        _seen_set.add(message_id)
        while len(_seen_ids) > MAX_SEEN_MESSAGES:
            old = _seen_ids.popleft()
            _seen_set.discard(old)
        return False


def log_revocation(data):
    subscription = data.get("subscription") or {}
    print(
        "[Server] EventSub revoked:"
        f" type={subscription.get('type')}"
        f" status={subscription.get('status')}"
        f" id={subscription.get('id')}"
    )


def route_channel_point_reward(event):
    """Send a redemption to its effect. Existing titles stay an exact match."""

    reward_title = (event.get("reward") or {}).get("title", "")
    username = (event.get("user_name") or "").lower()

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

    elif isinstance(reward_title, str) and reward_title.strip().lower() == clip_reward_title().lower():
        print(f"🎬 Play a Clip redeemed by {event.get('user_name') or username}!")
        Thread(
            target=play_clip_for,
            args=(
                event.get("user_name") or "",
                event.get("user_login") or "",
                reward_title if isinstance(reward_title, str) else "",
            ),
            daemon=True,
        ).start()


def handle_notification(sub_type, event):
    if not isinstance(event, dict):
        event = {}

    if sub_type == "channel.channel_points_custom_reward_redemption.add":
        reward = event.get("reward") or {}
        publish(
            "redemption",
            reward=reward.get("title", "") or "",
            reward_id=reward.get("id", "") or "",
            redemption_id=event.get("id", "") or "",
            user=event.get("user_name", "") or "",
            login=event.get("user_login", "") or "",
            input=censor_viewer_text(event.get("user_input") or ""),
        )
        route_channel_point_reward(event)
        return

    if sub_type == "channel.follow":
        user = event.get("user_name") or ""
        login = event.get("user_login") or ""
        publish("follow", user=user, login=login)
        if user or login:
            add_credit("follows", user=user, login=login)
        return

    if sub_type == "channel.subscribe":
        user, login = viewer_name(event)
        publish("sub", user=user, login=login, amount=1, months=1)
        add_credit("subs", user=user, login=login)
        return

    if sub_type == "channel.subscription.message":
        user, login = viewer_name(event)
        months = event.get("cumulative_months") or 0
        amount = event.get("duration_months") or 1
        publish("resub", user=user, login=login, amount=amount, months=months)
        add_credit("subs", user=user, login=login)
        return

    if sub_type == "channel.subscription.gift":
        user, login = viewer_name(event)
        amount = event.get("total") or 0
        publish("gift", user=user, login=login, amount=amount)
        add_credit("gifts", user=user, login=login, amount=amount or None)
        return

    if sub_type == "channel.cheer":
        user, login = viewer_name(event)
        amount = event.get("bits") or 0
        publish("bits", user=user, login=login, amount=amount)
        add_credit("bits", user=user, login=login, amount=amount or None)
        return

    print(f"[Server] No handler for EventSub type: {sub_type}")


@app.route("/webhook", methods=["POST"])
def webhook():
    raw_body = request.get_data() or b""

    if not signature_matches(raw_body):
        print("[Server] Rejected webhook: bad signature")
        return jsonify({"error": "invalid signature"}), 403

    message_id = request.headers.get("Twitch-Eventsub-Message-Id", "")
    timestamp = request.headers.get("Twitch-Eventsub-Message-Timestamp", "")
    if not message_id or timestamp_is_stale(timestamp):
        print("[Server] Rejected webhook: stale or incomplete message")
        return jsonify({"error": "stale or incomplete message"}), 403

    if already_seen(message_id):
        return "", 204

    try:
        data = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError:
        return jsonify({"error": "invalid json"}), 400
    if not isinstance(data, dict):
        data = {}

    message_type = request.headers.get("Twitch-Eventsub-Message-Type", "")

    if message_type == "webhook_callback_verification":
        challenge = data.get("challenge", "")
        if not isinstance(challenge, str):
            challenge = ""
        return Response(challenge, status=200, mimetype="text/plain")

    if message_type == "revocation":
        log_revocation(data)
        return jsonify({"message": "revocation received"}), 200

    if message_type == "notification":
        event = data.get("event") or {}
        sub_type = (data.get("subscription") or {}).get("type", "")
        print("EventSub event received:")
        print(json.dumps(event, indent=2))
        handle_notification(sub_type, event)
        return jsonify({"message": "Event received"}), 200

    print(f"[Server] Unknown EventSub message type: {message_type}")
    return jsonify({"message": "ignored"}), 200


# =============================
# SUBSCRIBE TO EVENTSUB
# =============================

EVENTSUB_URL = "https://api.twitch.tv/helix/eventsub/subscriptions"


def subscribe_event(sub_type, version, condition):
    """One Helix subscription. Same headers and webhook transport every time."""

    secret = get_eventsub_secret()
    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {TWITCH_OAUTH_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "type": sub_type,
        "version": version,
        "condition": condition,
        "transport": {
            "method": "webhook",
            "callback": WEBHOOK_URL,
            "secret": secret,
        },
    }

    print(f"Sending EventSub subscription request for {sub_type}...")

    try:
        response = requests.post(
            EVENTSUB_URL,
            headers=headers,
            json=payload,
            timeout=15,
        )
    except requests.RequestException as exc:
        print(f"❌ EventSub request error for {sub_type}: {exc}")
        return

    if response.status_code in (200, 202):
        print(f"✅ EventSub subscription successful: {sub_type}")
    elif response.status_code == 409:
        print(f"✅ Already subscribed: {sub_type}")
    else:
        print(f"❌ EventSub subscription failed: {sub_type}")
        print(response.status_code)
        print(response.text)


def subscribe_to_events():
    """Subscribe on startup. The token in TWITCH_OAUTH_TOKEN must have the scopes in the README."""

    if not TWITCH_CLIENT_ID or not TWITCH_OAUTH_TOKEN:
        print("❌ TWITCH_CLIENT_ID or TWITCH_OAUTH_TOKEN is missing. Skipping subscriptions.")
        return
    if not WEBHOOK_URL:
        print("❌ WEBHOOK_URL is missing. Skipping subscriptions.")
        return
    if not get_eventsub_secret():
        print("❌ EVENTSUB_SECRET or SECRET is missing. Skipping subscriptions.")
        return

    broadcaster = {"broadcaster_user_id": BROADCASTER_USER_ID}
    # Follow v2 also needs the moderator. For a streamer token, that is the same id.
    follow_condition = {
        "broadcaster_user_id": BROADCASTER_USER_ID,
        "moderator_user_id": BROADCASTER_USER_ID,
    }

    subscribe_event("channel.channel_points_custom_reward_redemption.add", "1", broadcaster)
    subscribe_event("channel.follow", "2", follow_condition)
    subscribe_event("channel.subscribe", "1", broadcaster)
    subscribe_event("channel.subscription.gift", "1", broadcaster)
    subscribe_event("channel.subscription.message", "1", broadcaster)
    subscribe_event("channel.cheer", "1", broadcaster)


# =============================
# MAIN
# =============================

if __name__ == "__main__":
    print("Starting Production Center server...")

    subscribe_to_events()

    try:
        app.run(
            host="0.0.0.0",
            port=5000,
            debug=False,
            use_reloader=False,
        )

    finally:
        stop_archive()
