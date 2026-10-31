# Production Center spec: translation for the Night Elf Translator (`GET /translate`)

For: Production Center Manager. Target: `Server.py` in ProductionCenter2.0 (Flask, port 5000).
Builds on the earlier spec (`GET /events` redemption feed + `GET /tts`). The widget needs no new EventSub subscriptions:
it reads the existing `redemption` events (`reward`, `reward_id`, `redemption_id`, `user`, `login`, `input`) from `/events`.

## Twitch side (Tyler, in the Creator Dashboard)
Create two channel point rewards with **"Require viewer to enter text"** ON:
- `Translate to English`: prompt "Type something in Spanish, Portuguese, French, Japanese, Korean, Chinese, German or Dutch"
- `Translate from English`: prompt "Language + text, e.g. spanish: hello chat"

## Contract
`GET http://localhost:5000/translate?text=...&target=en&source=` -> `200 application/json`
```json
{"text": "Hi chat! How is everyone tonight?", "source": "es", "target": "en", "detected": "es"}
```
- `target` (required) one of: `en, es, pt-BR, pt, fr, ja, ko, zh-Hans, zh-Hant, de, nl` (case-insensitive). Else 400.
- `source` optional (widget sends `en` for "from English"; omits it for "to English" so the backend auto-detects).
- `detected` = language the engine detected (lowercase ISO, e.g. `es`, `zh`, `pt`). The widget picks Simplified vs Traditional itself if it only gets `zh`.
- `text` trimmed, max 300 chars (413 if longer; widget already clips to 200).
- Headers: `Access-Control-Allow-Origin: *` (widgets load from file://), `Cache-Control: no-store`.
- Cache results in memory (LRU ~500, key = target|source|text) so repeats cost zero characters.
- Any engine error/timeout -> `502` (widget shows "my tome is closed" and moves on). Timeout 8 s on the widget side.

## Engine: free Google Translate (default, no key) — same engine as Tyler's old `ChatBeacon/interpreter.py`
Tyler's old interpreter used `deep_translator.GoogleTranslator(source="auto", ...)`, free with no key. That library
doesn't report the detected language, so this calls the same free Google endpoint it's built on
(`translate.googleapis.com/translate_a/single?client=gtx`), which returns the translation AND the detected language.
Verified 2026-10-30: "Bonjour tout le monde" -> "Hello everyone", detected `fr`. Unofficial (no SLA, rate-limited if hammered),
which is fine for channel-point volume. Google codes: `en es pt fr ja ko zh-CN zh-TW de nl`.
Fallback chain: Google -> MyMemory (no key, ~5,000 chars/day) -> DeepL only if `DEEPL_API_KEY` is set (optional, 500k chars/month free).

## Ready-to-paste (Server.py)
```python
import os, requests
from collections import OrderedDict
from flask import request, jsonify, abort

TR_MAX = 300
TR_CACHE = OrderedDict()
TR_TARGETS = {  # widget code -> (Google/MyMemory code, DeepL target)
    "en": ("en", "EN-US"), "es": ("es", "ES"), "pt": ("pt", "PT-BR"), "pt-br": ("pt", "PT-BR"),
    "fr": ("fr", "FR"), "ja": ("ja", "JA"), "ko": ("ko", "KO"), "zh-hans": ("zh-CN", "ZH-HANS"),
    "zh-hant": ("zh-TW", "ZH-HANT"), "de": ("de", "DE"), "nl": ("nl", "NL"),
}

def _google(text, target, source):
    r = requests.get("https://translate.googleapis.com/translate_a/single", timeout=6,
                     params={"client": "gtx", "sl": source or "auto", "tl": target, "dt": "t", "q": text})
    r.raise_for_status(); j = r.json()
    out = "".join(seg[0] for seg in j[0] if seg and seg[0])
    if not out: raise RuntimeError("empty google result")
    return out, (j[2] or source or "").lower()

def _mymemory(text, target, source):
    r = requests.get("https://api.mymemory.translated.net/get", timeout=6,
                     params={"q": text, "langpair": f"{source or 'autodetect'}|{target}"})
    r.raise_for_status(); j = r.json()
    if j.get("responseStatus") != 200 or j.get("quotaFinished"): raise RuntimeError(j.get("responseDetails"))
    d = j["responseData"]
    return d["translatedText"], (d.get("detectedLanguage") or source or "").lower()

def _deepl(text, target, source):
    key = os.environ["DEEPL_API_KEY"]
    host = "https://api-free.deepl.com" if key.endswith(":fx") else "https://api.deepl.com"
    data = {"text": [text], "target_lang": target}
    if source: data["source_lang"] = source.split("-")[0].upper()
    r = requests.post(host + "/v2/translate", json=data,
                      headers={"Authorization": "DeepL-Auth-Key " + key}, timeout=6)
    r.raise_for_status(); t = r.json()["translations"][0]
    return t["text"], t.get("detected_source_language", "").lower()

@app.route("/translate")
def translate():
    text = " ".join((request.args.get("text") or "").split())
    target = (request.args.get("target") or "").lower()
    source = (request.args.get("source") or "").lower() or None
    if not text or target not in TR_TARGETS: abort(400)
    if len(text) > TR_MAX: abort(413)
    ck = f"{target}|{source}|{text}"
    if ck in TR_CACHE:
        TR_CACHE.move_to_end(ck); out = TR_CACHE[ck]
    else:
        g_t, deepl_t = TR_TARGETS[target]
        src = TR_TARGETS.get(source, (source, None))[0] if source else None
        engines = [lambda: _google(text, g_t, src), lambda: _mymemory(text, g_t, src)]
        if os.getenv("DEEPL_API_KEY"): engines.append(lambda: _deepl(text, deepl_t, source))
        res = None
        for eng in engines:
            try: res, det = eng(); break
            except Exception as e: app.logger.info("translate engine failed: %s", e)
        if res is None: abort(502)
        out = {"text": res, "source": source or det, "target": target, "detected": det}
        TR_CACHE[ck] = out
        if len(TR_CACHE) > 500: TR_CACHE.popitem(last=False)
    resp = jsonify(out)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Cache-Control"] = "no-store"
    return resp
```
Note: Flask `abort()` responses don't carry the CORS header; the widget treats any failed fetch as "tome closed", so that's fine.

## `/tts` voice allowlist: add these (all verified in edge-tts's voice list)
```python
TTS_VOICES |= {"es-MX-DaliaNeural", "pt-BR-FranciscaNeural", "fr-FR-DeniseNeural", "ja-JP-NanamiNeural",
               "ko-KR-SunHiNeural", "zh-CN-XiaoxiaoNeural", "zh-TW-HsiaoChenNeural", "de-DE-KatjaNeural",
               "nl-NL-ColetteNeural", "en-US-AriaNeural"}
```
No other /tts changes needed: the widget sends `rate=+0%&pitch=+0Hz` and translations stay under 300 chars.

## Notes / concerns
- Keys stay in `.env`; nothing secret is sent to the widget. Keep `/translate` and `/tts` on localhost, not through the webhook tunnel (anyone could burn the DeepL quota).
- Viewer text is user input: it's only passed to DeepL/MyMemory and displayed as text (the widget never renders it as HTML).
- Twitch's own AutoMod doesn't filter reward text, so a viewer could get her to translate something rude. Optional: run the existing banned-words list (if any) over `input` before publishing to `/events`.
