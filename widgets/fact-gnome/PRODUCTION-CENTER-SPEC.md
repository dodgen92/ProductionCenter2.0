# Production Center spec: shared widget event feed (`GET /events`)

For: Production Center Manager. Target: `Server.py` in dodgen92/ProductionCenter2.0 (Flask, port 5000).
Goal: ONE local feed that every Stream-Widget polls. The Fact Gnome is the first consumer.

## What exists today
- `POST /webhook` already receives EventSub `channel.channel_points_custom_reward_redemption.add` (v1),
  subscribed at startup by `subscribe_to_channel_points()` (webhook transport, `WEBHOOK_URL`, `SECRET`).
- Scope needed on `TWITCH_OAUTH_TOKEN`: `channel:read:redemptions` (already required for the current sub).
- No websocket/Socket.IO and no CORS. Nothing to subscribe newly for the gnome.

## Add (no new server, no new libraries)
1. An in-memory ring buffer + lock:
```python
from collections import deque
EVENTS = deque(maxlen=200); EVENT_ID = 0; EVENTS_LOCK = threading.Lock()
def publish(etype, **fields):
    global EVENT_ID
    with EVENTS_LOCK:
        EVENT_ID += 1
        EVENTS.append({"id": EVENT_ID, "type": etype, "ts": time.time(), **fields})
```
2. In `webhook()`, inside the `notification` branch, BEFORE the `if reward_title == ...` chain (so every reward is published, existing behavior unchanged):
```python
sub_type = data.get("subscription", {}).get("type", "")
if sub_type == "channel.channel_points_custom_reward_redemption.add":
    publish("redemption",
            reward=event.get("reward", {}).get("title", ""),
            reward_id=event.get("reward", {}).get("id", ""),
            redemption_id=event.get("id", ""),
            user=event.get("user_name", ""),          # display name, NOT lowercased
            login=event.get("user_login", ""),
            input=event.get("user_input", ""))
```
3. New route:
```python
@app.route("/events")
def events():
    since = request.args.get("since", default=0, type=int)
    with EVENTS_LOCK:
        out = [e for e in EVENTS if e["id"] > since]; last = EVENT_ID
    resp = jsonify({"last_id": last, "events": out})
    resp.headers["Access-Control-Allow-Origin"] = "*"   # widgets load from file:// (origin "null")
    resp.headers["Cache-Control"] = "no-store"
    return resp
```

## Exact contract the widget expects
`GET http://localhost:5000/events?since=N` ->
```json
{"last_id": 42, "events": [
  {"id": 42, "type": "redemption", "ts": 1761800000.0, "reward": "Gnome Fact",
   "reward_id": "uuid", "redemption_id": "uuid", "user": "RemyFriend", "login": "remyfriend", "input": ""}
]}
```
- Widgets call `since=-1` first, take `last_id` (backlog is skipped), then poll every ~1s with the highest id seen.
- `id` must be strictly increasing. `last_id` is returned even when `events` is empty.
- Gnome matches `reward` to its `?reward=` param case-insensitively (default "Gnome Fact").

## Later (same feed, same shape; just more `publish()` calls + EventSub subs)
`follow` (channel.follow v2, moderator:read:followers), `sub`/`resub`/`gift` (channel:read:subscriptions),
`bits` (bits:read), `raid`, `hype_train`, `ad_break`, `chat` / `chat_delete` / `ban`.
Field names: always `user`, `login`, plus type-specific fields (`amount`, `months`, `viewers`, `text`, `message_id`).

## Notes / concerns
- Webhook needs a public HTTPS `WEBHOOK_URL` (tunnel); `/events` itself is only hit locally by OBS.
- `webhook()` does not verify the `Twitch-Eventsub-Message-Signature` HMAC with `SECRET`. Recommend adding it, and ignoring duplicate `Twitch-Eventsub-Message-Id` (Twitch retries), so redemptions aren't double-published.
- Keep tokens in `.env` only; nothing secret goes into `/events` or widget code.

## Follows for paladin-sub (next publish() call)
Subscribe EventSub `channel.follow` **version 2** (condition `broadcaster_user_id` + `moderator_user_id`; scope `moderator:read:followers`) and publish
`{"id": N, "type": "follow", "ts": ..., "user": event.user_name, "login": event.user_login}` to the same `/events` feed (same format, no new route).
paladin-sub also accepts `sub`/`resub`/`gift`/`bits`/`raid` from the feed (fields `user`, `login`, `amount`, `months`, `viewers`), but only while its IRC link is down, and it dedupes type+name within 30s.

---

# Addition: live TTS for widgets (`GET /tts`)

The Fact Gnome (and later any widget) asks the Production Center to speak. The engine and any key live
ONLY on the backend; widgets hold no secrets.

- **Default engine: `edge-tts`** (free, Microsoft Edge neural voices, no API key). `pip install edge-tts`
  (needs internet; it calls Microsoft's public read-aloud service, which is unofficial and could change).
- **Optional: ElevenLabs** if `ELEVENLABS_API_KEY` (and optionally `ELEVENLABS_VOICE_ID`) is in `.env`. Paid per character; the cache keeps the 76 facts to one charge each.

## Contract
`GET http://localhost:5000/tts?text=...&voice=en-US-AriaNeural&rate=+8%&pitch=+10Hz` -> `200 audio/mpeg`
- `text` required, trimmed, max 300 chars (413 if longer). `voice` must be in the allowlist (else default).
- `rate` like `+12%` / `-5%` (range -50..+50), `pitch` like `+15Hz` (-50..+60). Bad values -> defaults.
- Headers: `Access-Control-Allow-Origin: *` (widgets are file://), `Cache-Control: public, max-age=86400`.
- Disk cache `tts_cache/<sha1>.mp3` keyed by engine+voice+rate+pitch+text. Errors -> 502 (widget falls back to the browser voice after 4s).

## Ready-to-paste (Server.py)
```python
import asyncio, hashlib, os, re, requests
from flask import request, Response, abort
import edge_tts

TTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tts_cache")
os.makedirs(TTS_DIR, exist_ok=True)
TTS_VOICES = {"en-US-AnaNeural", "en-US-JennyNeural", "en-US-AriaNeural", "en-GB-MaisieNeural",
              "en-US-AshleyNeural", "en-GB-SoniaNeural", "en-AU-NatashaNeural"}
TTS_DEFAULT = "en-US-AriaNeural"
TTS_MAX = 300

def _edge_tts_bytes(text, voice, rate, pitch):
    async def run():
        out = bytearray()
        async for chunk in edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).stream():
            if chunk["type"] == "audio":
                out += chunk["data"]
        return bytes(out)
    return asyncio.run(run())          # Flask handler threads have no running loop, so this is safe

def _eleven_bytes(text):
    vid = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
    r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{vid}",
                      headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "accept": "audio/mpeg"},
                      json={"text": text, "model_id": "eleven_turbo_v2_5"}, timeout=20)
    r.raise_for_status(); return r.content

@app.route("/tts")
def tts():
    text = " ".join((request.args.get("text") or "").split())
    if not text: abort(400)
    if len(text) > TTS_MAX: abort(413)
    voice = request.args.get("voice") or TTS_DEFAULT
    if voice not in TTS_VOICES: voice = TTS_DEFAULT
    rate = request.args.get("rate", "+0%");  pitch = request.args.get("pitch", "+0Hz")
    m = re.fullmatch(r"([+-])(\d{1,2})%", rate);   rate = rate if m and int(m[2]) <= 50 else "+0%"
    m = re.fullmatch(r"([+-])(\d{1,2})Hz", pitch); pitch = pitch if m and int(m[2]) <= 60 else "+0Hz"
    engine = "eleven" if os.getenv("ELEVENLABS_API_KEY") and request.args.get("engine") == "eleven" else "edge"
    key = hashlib.sha1(f"{engine}|{voice}|{rate}|{pitch}|{text}".encode()).hexdigest()
    path = os.path.join(TTS_DIR, key + ".mp3")
    if not os.path.exists(path):
        try:
            data = _eleven_bytes(text) if engine == "eleven" else _edge_tts_bytes(text, voice, rate, pitch)
            if not data: raise RuntimeError("no audio")
        except Exception as e:
            app.logger.warning("tts failed: %s", e); abort(502)
        with open(path + ".tmp", "wb") as f: f.write(data)
        os.replace(path + ".tmp", path)
    with open(path, "rb") as f: data = f.read()
    resp = Response(data, mimetype="audio/mpeg")
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp
```
Notes: `requests` only needed for the ElevenLabs path. First request per fact takes ~1-2 s; cached repeats are instant.
Requests to the widget default to engine edge; ElevenLabs is opt-in with `&engine=eleven` (widget param `?engine=` can be added later).
Keep `/tts` on localhost; don't expose it through the webhook tunnel (anyone could burn your ElevenLabs credits).
