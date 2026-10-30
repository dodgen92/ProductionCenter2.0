# 🎬 Production Center

**A live-stream control room that lets Twitch chat run the show.** Viewers spend channel points, and Production Center reacts in real time: it flips camera filters, rips animated Pokémon cards onto the screen, starts or stops automatic clipping that posts highlights straight to Discord, and can roll a random channel clip with an orc voice line.

Widgets on this PC (the Fact Gnome, the translator, the orc, end credits) read one local feed from this server. The server connects out to Twitch EventSub over a WebSocket. Twitch does not call back into this PC.

> 📸 **Demo:** _GIF or screenshot coming soon_
> <!-- Drop a GIF of a redemption firing on stream here, e.g. ![Demo](docs/demo.gif) -->

---

## ✨ What it does

| Channel point reward | What happens on stream |
|---|---|
| **Add Camera Filter** | Applies a random camera filter (via AutoHotkey hotkeys), then clears it after 3 minutes. |
| **Rip a Vintage Pokémon Card** | Pulls a random Gen 1 card the viewer hasn't caught yet, slides it across the screen with an eased OBS animation, and shows their progress toward all 151. Each viewer's collection is saved. |
| **Start** / **Stop** | Starts or stops an auto-clipping loop that creates Twitch clips on a timer and posts each one to a Discord channel. |
| **Play a Clip** | Picks a random clip from your channel and a random file from `voice_lines/orc/`, then publishes a `clip` event for the orc widget. The title match ignores case. Rename it with `CLIP_REWARD_TITLE` if you want. |
| **Translate to English** / **Translate from English** | Not handled inside the reward `if` chain. Every redemption is published on `/events` (including the viewer's text). The translator widget sees those and calls `/translate` and `/tts`. Create both rewards with "Require viewer to enter text" turned on. |

Follows, subs, resubs, gifted subs, and cheers are published on the same feed and collected for the end-credits roll.

## 🧠 Why it's interesting

Production Center ties **five separate systems** together into one real-time pipeline:

```mermaid
flowchart LR
    V[Viewer redeems reward] --> T[Twitch EventSub]
    T -->|WebSocket| F[Flask server on this PC]
    F --> O[OBS WebSocket<br/>scene animations]
    F --> A[AutoHotkey<br/>camera filters]
    F --> H[Twitch Helix API<br/>clip creation]
    H --> D[Discord webhook]
```

- **Event-driven:** This PC opens one WebSocket to Twitch. Events arrive the moment they happen. There is no polling for redemptions, and no public URL.
- **Non-blocking:** Each effect runs on its own thread or process, so a 3-minute filter never stalls the next redemption.
- **Process management:** The clipping loop runs as a supervised child process with safe start, stop, and force-kill handling.
- **Persistent game state:** Per-viewer Pokémon collections survive between streams.
- **One local feed:** Widgets poll `GET /events`. They do not hold Twitch tokens.

## 🛠️ Tech used

- **Python 3** with **Flask** (local server on `127.0.0.1:5000`)
- **Twitch EventSub WebSocket** via `websocket-client` (redemptions, follows, subs, cheers) and **Twitch Helix API** (subscriptions and clips)
- **OBS WebSocket v5** via `obsws-python` (scene item animation and text updates)
- **edge-tts** (free neural voices for widgets). ElevenLabs is optional.
- **AutoHotkey** (camera filter hotkeys)
- **Discord webhooks** (clip notifications)
- **Pillow** (`sheetripper.py` slices card sheets into individual card images)

## 📁 Project layout

```
Server.py              Flask server: EventSub WebSocket, feed, TTS, translate, credits
archive.py             Auto-clipping loop (Twitch Helix) + Discord posting
clips.py               App access token + Helix clip lookups
Pokemon/pokerip.py     Pokémon card pull logic + OBS animation
pokemon_catches.json   Saved per-viewer collections
credits.html           End-credits page for an OBS browser source
banned_words.txt       Optional whole-word filter (empty = off)
voice_lines/orc/       Drop recorded mp3/wav lines here
                           Widgets stay in WIDGETS_DIR (not in this repo)
CameraFilters/         Random filter picker, clear script, AutoHotkey filter hotkeys
sheetripper.py         Utility: cut card sheets into single card images
unsubscribe.py         Utility: remove EventSub subscriptions (WebSocket or old webhook)
tests/                 Example pytest tests and a short guide
```

`tts_cache/` and `stream_credits.json` are created at runtime and gitignored. `stream_credits.json` holds viewer display names for the current roll.

## 🔐 Twitch scopes and how subscribing works

On startup the server opens a WebSocket to `wss://eventsub.wss.twitch.tv/ws` (or `EVENTSUB_WS_URL`, if you set one). When Twitch sends `session_welcome`, `subscribe_to_events()` registers one subscription per event type on that session. It does not open a Twitch login window. It sends your existing user token to Helix:

```http
POST https://api.twitch.tv/helix/eventsub/subscriptions
Client-ID: <TWITCH_CLIENT_ID>
Authorization: Bearer <TWITCH_OAUTH_TOKEN>
```

The JSON body sets the transport to `websocket` and includes the `session_id` from the welcome message. There is no callback URL and no signing secret.

`TWITCH_OAUTH_TOKEN` must be a **user** access token for the broadcaster. An **app** access token will not work for these WebSocket subscriptions. Generate a new user token when you add scopes. With the [Twitch CLI](https://dev.twitch.tv/docs/cli/):

```bash
twitch token -u -s "channel:read:redemptions moderator:read:followers channel:read:subscriptions bits:read"
```

Put the access token in `TWITCH_OAUTH_TOKEN` and the app's client id in `TWITCH_CLIENT_ID`.

| Scope | Used for |
|---|---|
| `channel:read:redemptions` | Channel point redemptions (`channel.channel_points_custom_reward_redemption.add` v1) |
| `moderator:read:followers` | Follows (`channel.follow` v2) |
| `channel:read:subscriptions` | Subs, resubs, and gifted subs |
| `bits:read` | Cheers (`channel.cheer` v1) |

Follow v2 also sends `moderator_user_id`. This server sets that to `BROADCASTER_USER_ID`, so the token has to belong to the broadcaster (you are always a mod on your own channel).

Play a Clip does **not** use that user token. It uses an app token from `clips.py` (`client_credentials`), which needs `TWITCH_CLIENT_ID` plus `TWITCH_CLIENT_SECRET` (the client secret from the Twitch developer console). Reading clips does not add another scope on the user token.

### What you need to change

1. Copy any new keys from `.env.example` into `.env`. Names only live in the example file. Never commit `.env`.
2. Delete `WEBHOOK_URL` and `EVENTSUB_SECRET` from `.env`. The server does not read them anymore. You can uninstall ngrok.
3. Run `python unsubscribe.py` once. That deletes subscriptions left over from the old webhook, including any that still point at an old public address. WebSocket subscriptions also end when the server disconnects.
4. Set `TWITCH_CLIENT_SECRET` to the app client secret. `clips.py` reads that for Play a Clip. If you leave it blank, `clips.py` still falls back to `SECRET`. Keep `SECRET` when that fallback is the client secret you still use.
5. `TWITCH_OAUTH_TOKEN` must be a **user** token for your channel with all four scopes above. An app token will not create the WebSocket subscriptions. A token that only has `channel:read:redemptions` will keep redemptions working and Twitch will reject the other subscriptions (the server prints the error and keeps going).
6. Leave `EVENTSUB_WS_URL` blank for real Twitch. Set it only when you point the client at the Twitch CLI mock (see below).
7. Create the channel point rewards in the Creator Dashboard (table above). Titles for the old rewards must match exactly. **Play a Clip** ignores case.
8. Drop at least one `.mp3` or `.wav` in `voice_lines/orc/` if you want the orc to talk. With zero files the clip event is still published and `voice_line` is empty. The clip event also includes `reward` (the channel-point title) so a widget can filter on `?reward=`.
9. Set `WIDGETS_DIR` to your Stream-Widgets folder. On this PC that is `C:\Users\tyler\Desktop\Stream-Widgets`. The server does not bake that path in. If the variable is blank or the folder is not there, `/widgets/...` returns 404 and prints why.
10. Optional: `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` for `/tts?engine=eleven`. Optional: `DEEPL_API_KEY` as the last translation fallback. Optional: add lines to `banned_words.txt`.

`/translate` tries, in order: Google's free `translate.googleapis.com` `client=gtx` endpoint (no key), then [MyMemory](https://mymemory.translated.net/) (no key), then DeepL only if `DEEPL_API_KEY` is set. The Google endpoint is unofficial. It can change or rate-limit, which is why the fallbacks exist.

## 🚀 How to run it

### 1. Prerequisites
- Windows, Python 3.10+, [OBS Studio](https://obsproject.com/) with WebSocket server enabled, and [AutoHotkey](https://www.autohotkey.com/) v1
- A Twitch application ([dev.twitch.tv/console](https://dev.twitch.tv/console)) and the channel point rewards in the table above
- A user token with the four scopes in the section above

### 2. Install
```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure your secrets
```bash
copy .env.example .env
```
Fill in `.env` with your own Twitch, Discord, and OBS values. **`.env` is git-ignored; never commit it.**

Names in `.env.example`:

| Name | Required? | What it is |
|---|---|---|
| `EVENTSUB_WS_URL` | No | WebSocket address. Blank means `wss://eventsub.wss.twitch.tv/ws`. |
| `TWITCH_CLIENT_SECRET` | For Play a Clip and `clips.py` | App client secret from the Twitch console. Falls back to `SECRET`. |
| `CLIP_REWARD_TITLE` | No | Reward title to listen for. Blank means `Play a Clip`. |
| `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID` | No | Paid TTS. Blank uses edge-tts. |
| `DEEPL_API_KEY` | No | Last translation engine. Blank skips DeepL. |
| `WIDGETS_DIR` | For HTML widgets | Full path to the widgets folder. On this PC that is `C:\Users\tyler\Desktop\Stream-Widgets`. Blank means `/widgets/...` returns 404. |
| `GEMINI_API_KEY` | For Benito and Ask the Monk | Same key Benito already uses. The monk returns a canned saying if it is blank. |
| `COUNSEL_MODEL` | No | Blank means `gemini-2.5-flash-lite`. |
| `COUNSEL_USER_COOLDOWN` | No | Seconds between Gemini answers for one viewer. Blank means 60. |
| `COUNSEL_DAILY_CAP` | No | Monk calls per local day. Blank means 100. |
| `GEMINI_PROJECT_DAILY_CAP` | No | Monk + Benito calls per local day. Blank means 900, so a busy night leaves room for Benito. |

### 4. Launch
```bash
python Server.py
```

The server listens on `127.0.0.1:5000` only. Point OBS and widgets at `http://localhost:5000` or `http://127.0.0.1:5000`. A request with `X-Forwarded-For` or `X-Forwarded-Host`, or from any other machine, gets 403.

You should see a welcome line with a session id, then one `subscribed` line per event type (or `Already subscribed` if that type was already active). Redeem a reward on your channel to test it.

If the socket drops, the client waits and tries again. The wait doubles each time and stops growing at 30 seconds. A fresh session creates the subscriptions again. If Twitch sends `session_reconnect`, the client connects to the new URL, keeps the subscriptions it already has, and closes the old socket only after the new welcome.

### 5. Optional: fire events with the Twitch CLI mock

Leave `EVENTSUB_WS_URL` blank for a real channel. To practice without redeeming, the [Twitch CLI](https://dev.twitch.tv/docs/cli/websocket-event-command) can pretend to be EventSub.

In one terminal:

```bash
twitch event websocket start-server
```

The mock prints `Connect to the WebSocket server at: ws://127.0.0.1:8080/ws`. Put that in `.env`:

```
EVENTSUB_WS_URL=ws://127.0.0.1:8080/ws
```

Start `python Server.py` and wait for the welcome line. In another terminal, with the server still running:

```bash
twitch event trigger channel.follow --transport=websocket
twitch event trigger channel.channel_points_custom_reward_redemption.add --transport=websocket
```

The trigger reaches every client connected to the mock. You can target one session with `--session=` and the id from the welcome line.

Subscription POSTs still go to real Twitch Helix. The mock's session id is not a real Twitch session, so those lines usually fail while you are on the mock. The trigger is still delivered. Clear `EVENTSUB_WS_URL` when you want real Twitch again. Real `subscribed` lines are the check that your user token and scopes are right.

### 6. End credits in OBS
1. In OBS, add a **Browser** source. Do not check "Local file".
2. URL: `http://localhost:5000/credits`
3. Width `1920`, height `1080`.
4. Check **Shutdown source when not visible** and **Refresh browser when scene becomes active** if you want a clean crawl each time you show it.
5. The page background is transparent. Leave custom CSS empty unless you want to restyle it.
6. The page polls `http://localhost:5000/credits.json` every few seconds and scrolls Subs, Gifted Subs, Bits, and Follows like movie credits.
7. At the start of the next stream, clear the roll from this PC:

```bash
curl -X POST http://127.0.0.1:5000/credits/reset
```

Someone who receives a gifted sub is listed under Subs. The person who sent the gifts is listed under Gifted Subs. Anonymous cheers and gifted subs have no Twitch username. They are stored as one **Anonymous** line per group, and the amounts add up, because the server cannot tell those viewers apart.

### 7. Word filter
`banned_words.txt` is a plain list, one word or phrase per line. Lines starting with `#` are comments. The file ships with no words, so nothing is filtered until you add one. Matching is case-insensitive and whole-word. Hits are replaced with stars in redemption text before it is published, and again on `/translate` and `/tts`. Usernames are not filtered. If the file is missing or unreadable, text is left alone.

### 8. Widgets in OBS
Twitch will not play a clip embed on a `file://` page. Add each widget as a **Browser** source (not a local file):

```
http://localhost:5000/widgets/<widget>/index.html
```

`<widget>` is the folder name inside `WIDGETS_DIR`. Example, if the orc presenter lives in a folder named `orc-clip`:

```
http://localhost:5000/widgets/orc-clip/index.html
```

Use `http://127.0.0.1:5000/...` if `localhost` misbehaves. The route only serves files inside `WIDGETS_DIR` (`send_from_directory` blocks `..`). Responses send `Cache-Control: no-store`, so an OBS "Refresh cache of current page" picks up edits.

### 9. Ask the Monk
Create a channel point reward named **Ask the Monk** with "Require viewer to enter text" on. The widget reads that redemption from `/events` and calls `GET /counsel`. The server uses the same `GEMINI_API_KEY` as Benito. It never sends the key to the widget. A blocked word, a viewer who just asked, a full daily cap, or any Gemini error returns one of 30 canned sayings (`"source": "canned"`) instead. Counts for the monk and Benito share `gemini_usage.json` (gitignored). The monk voice on `/tts` is `en-HK-SamNeural`.

```bash
curl "http://localhost:5000/counsel?q=tank%20or%20healer&user=test"
```

## 🧪 Tests

Example tests live in `tests/`. The guide in [`tests/README.md`](tests/README.md) explains what a unit test is, what a mock is, how to run them, and walks through one test line by line.

```bash
pip install -r requirements-dev.txt
pytest -v
```

---

Built by [Tyler Dodgen](https://github.com/dodgen92) to make streams more interactive.
