# Production Center spec: Pandaren Counselor (`GET /counsel`) + `/tts` voice

For: Production Center Manager. Target: existing `Server.py` (Flask, port 5000). Builds on the `/events` + `/tts` spec already sent.
Widget: `Stream-Widgets/monk-counselor/` (reward "Ask the Monk", viewer types a question). The widget never sees the key.

## 1. Nothing new for the trigger
The widget reads `type:"redemption"` events from `/events` (fields `reward`, `reward_id`, `redemption_id`, `user`, `login`, `input`), same as the gnome/translator.
Tyler creates the reward **"Ask the Monk"** with *Require viewer to enter text* ON.

## 2. `/tts` allowlist
Add **`en-HK-SamNeural`** to the `/tts` voice allowlist. The widget calls `/tts?text=...&voice=en-HK-SamNeural&rate=-5%&pitch=+0Hz` twice per redemption (question, then answer).

## 3. New route: `GET /counsel`
`GET http://localhost:5000/counsel?q=<question>&user=<display name>` ->
```json
{"answer": "1-3 sentences, under ~45 words", "source": "gemini"}
```
- `source` is `"gemini"` or `"canned"`. Always `200` with an answer when possible (canned on any problem); a non-200 or timeout (>12 s) makes the widget use its own local sayings.
- Headers: `Access-Control-Allow-Origin: *`, `Cache-Control: no-store` (widget runs from `file://`, origin `null`).
- Localhost only: the existing ngrok guard (403 for tunneled requests to anything but `POST /webhook`) covers it. Keep it that way: this route spends Gemini quota.

### Key + model
- Key from `.env`: **`GEMINI_API_KEY`** (no existing variable name for Gemini was documented anywhere I could see; if `Server.py`/Benito already reads one, reuse that name). Never log it, never return it.
- Model: a **Flash-Lite** model (e.g. `gemini-2.5-flash-lite`, or the current Flash-Lite); configurable via `COUNSEL_MODEL`. `max_output_tokens` ~120, `temperature` ~0.9.
- Free-tier limits are **per Google Cloud project, not per key**. If Benito uses the same project, they share RPM/RPD. Tyler can check caps at https://aistudio.google.com/rate-limit; a separate project for the monk isolates them.

### Guards (in this order)
1. `q = q.strip()[:200]`, `user = user[:25]`. Empty -> canned.
2. **Word filter**: reuse the translator's filter list if one exists; if `q` hits it -> canned answer (don't send to Gemini, don't echo). Also run the filter on Gemini's output; on a hit -> canned.
3. **Per-viewer cooldown**: `COUNSEL_USER_COOLDOWN` seconds (default 60) keyed by lowercase user -> canned.
4. **Daily cap**: `COUNSEL_DAILY_CAP` (default 100) Gemini calls per local day, counter resets at midnight. Make the counter **shared with Benito** (one `gemini_usage` counter/helper both features increment, stored in a small JSON file so restarts don't reset it) and have the monk stop at its cap OR when the shared total gets near the project's free RPD, so a busy night can't lock Benito out. Over cap -> canned.
5. Gemini call with a ~8 s timeout; any error/empty/blocked response -> canned.
6. Trim answer to ~300 chars at a sentence boundary.

### System prompt
```
You are Master Brewpaw, a warm, wise, and funny pandaren monk and brewmaster who gives counsel to viewers on
a World of Warcraft Twitch stream (channel: remyfriend). A viewer named {user} asks you a question.
Answer in 1-3 sentences, under 45 words total, in natural, fluent, modern English.
Be kind, playful, and genuinely helpful. Tea, brew, balance, and WoW metaphors are welcome; keep them light.
Never use broken or "accented" English, stereotypes, or fortune-cookie cliches like "Confucius say".
Keep it Twitch-safe: no profanity, sexual content, hate, or politics.
Do not give medical, legal, financial, or crisis advice. If the question touches self-harm, abuse, health,
or legal trouble, respond gently and encourage them to reach out to someone they trust or a professional or local
helpline. Never claim to be an AI; you are the monk. Do not repeat the question.
```

### Sketch
```python
import json, os, random, threading, time, datetime, requests
COUNSEL_CAP = int(os.getenv("COUNSEL_DAILY_CAP", "100"))
COUNSEL_CD = int(os.getenv("COUNSEL_USER_COOLDOWN", "60"))
COUNSEL_MODEL = os.getenv("COUNSEL_MODEL", "gemini-2.5-flash-lite")
_last_ask = {}; _usage_lock = threading.Lock()
USAGE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gemini_usage.json")

def gemini_usage(feature, bump=False):          # shared with Benito
    with _usage_lock:
        today = datetime.date.today().isoformat()
        try: u = json.load(open(USAGE_FILE))
        except Exception: u = {}
        if u.get("day") != today: u = {"day": today}
        if bump: u[feature] = u.get(feature, 0) + 1; json.dump(u, open(USAGE_FILE, "w"))
        return u.get(feature, 0), sum(v for k, v in u.items() if k != "day")

def _canned(): return jsonify_nc({"answer": random.choice(MONK_SAYINGS), "source": "canned"})
def jsonify_nc(o):
    r = jsonify(o); r.headers["Access-Control-Allow-Origin"] = "*"; r.headers["Cache-Control"] = "no-store"; return r

@app.route("/counsel")
def counsel():
    q = (request.args.get("q") or "").strip()[:200]; user = (request.args.get("user") or "friend")[:25]
    if not q or is_blocked(q): return _canned()          # is_blocked = word filter
    now = time.time(); k = user.lower()
    if now - _last_ask.get(k, 0) < COUNSEL_CD: return _canned()
    mine, total = gemini_usage("monk")
    if mine >= COUNSEL_CAP: return _canned()
    key = os.getenv("GEMINI_API_KEY")
    if not key: return _canned()
    _last_ask[k] = now
    try:
        r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{COUNSEL_MODEL}:generateContent",
            headers={"x-goog-api-key": key}, timeout=8, json={
              "system_instruction": {"parts": [{"text": MONK_PROMPT.format(user=user)}]},
              "contents": [{"role": "user", "parts": [{"text": q}]}],
              "generationConfig": {"maxOutputTokens": 120, "temperature": 0.9}})
        gemini_usage("monk", bump=True)
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        if not text or is_blocked(text): return _canned()
        return jsonify_nc({"answer": text[:300], "source": "gemini"})
    except Exception as e:
        app.logger.warning("counsel failed: %s", type(e).__name__); return _canned()
```

### Canned sayings (`MONK_SAYINGS`)
1. A cup poured in a hurry spills on the table. Slow down, and the answer will steep.
2. Even the strongest brew starts as plain water and patience.
3. When the path is foggy, take the next small step. The mist clears for walkers, not worriers.
4. Balance is not standing still. It is a hundred tiny wobbles, corrected with a smile.
5. Rest is part of the training. Bamboo grows in the quiet, too.
6. If the load is too heavy, share it. Even a monk calls friends to carry the keg.
7. You cannot pour from an empty kettle. Refill yourself first.
8. Mistakes are just practice wearing a disguise.
9. The loudest thought in your head is not always the wisest. Let it cool like tea.
10. Laugh at your stumbles. The ground is a patient teacher.
11. A wipe is only a lesson with a repair bill.
12. Drink some water, stretch your paws, then decide. Most choices taste better after a sip.
13. The best time to start was yesterday. The second best is after this cup.
14. Do not compare your first brew to another monk's hundredth.
15. Some days you are the tank, some days you are the floor. Both get back up.
16. Be gentle with yourself. You are the only body you get to level.
17. If you cannot decide, flip a coin. Your heart will tell you which side it hoped for.
18. Kindness is a brew that never goes stale.
19. Wisdom is knowing when to push, and knowing when to go make a snack.
20. A good friend is like a good tavern: warm, loud, and always open.
21. The mountain is climbed one ledge at a time, and with frequent tea breaks.
22. Worry is a rocking chair. Lots of motion, no distance.
23. Small habits are like small coins. Save enough and you can buy the epic mount.
24. Ask for help early. Pride has never once rezzed anyone.
25. A clear mind is like still water. Stop stirring and you will see the bottom.
26. Sleep on it. Tomorrow's you is better rested and slightly smarter.
27. Every master was once a level one with no idea what the buttons did.
28. Do one thing well, then the next. Even a brewmaster only stirs one keg at a time.
29. When in doubt, be kind, drink water, and log off at a reasonable hour.
30. The journey matters more than the loot. But the loot is nice, too.

### Test
`curl "http://localhost:5000/counsel?q=tank%20or%20healer&user=test"` -> JSON with `answer`/`source`. Then `?test=1` in OBS shows the full flow without Gemini.
