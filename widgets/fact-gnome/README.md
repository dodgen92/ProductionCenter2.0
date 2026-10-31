# Fact Gnome: "Gnome Fact" channel point reward

A painted gnome scholar (pink pigtails, teal coat, glowing tome) pops up in an arcane puff, reads a random WoW fact (trivia, dev easter eggs, player legends, all in her sassy voice) out loud while it types into her speech bubble, then hops away. Redemptions queue and play one after another. Facts come from a local list, so there are no AI calls. Her voice is LIVE neural TTS from the Production Center's `/tts` route (free `edge-tts`, no key); if that's down she falls back to a Windows voice within ~4s.

## OBS setup
1. Add a **Browser Source**, untick "Local file", URL
   `file:///C:/Users/tyler/Desktop/Stream-Widgets/fact-gnome/index.html?channel=remyfriend&reward=Gnome%20Fact`
2. Width 1920, height 1080; keep the default transparent CSS. Tick "Control audio via OBS" to put her voice in the mixer.
3. Preview anytime with `&test=1` (a fake redemption every 12s, no network).

## How she gets triggered
1. **Production Center (main way):** she polls `http://localhost:5000/events` on the existing Flask `Server.py` and fires on any `redemption` event whose reward title matches `?reward=` (case-insensitive). This catches every redemption, with or without viewer text. The backend change is described in `PRODUCTION-CENTER-SPEC.md`.
2. **Anonymous chat fallback:** Twitch chat only shows redemptions that **require viewer text**, and only by id. To use it, load once with `&learn=1`, redeem, copy the id into `&rewardid=…`. Same redemption from both sources only plays once.
3. **JS hook:** `window.factGnome.fire('Name')`.

## URL params
| Param | Default | Meaning |
|---|---|---|
| `channel` / `twitch` | – | Twitch channel (for the chat fallback) |
| `reward` | Gnome Fact | Reward title to match from the Production Center feed |
| `server` | http://localhost:5000 | Production Center address; `0` turns the feed off |
| `rewardid` | – | custom-reward-id for the chat fallback |
| `learn` | off | `1` shows ids of rewards redeemed with text |
| `cmd` / `cmdmods` | off | Chat command trigger like `!fact`; `cmdmods=1` = mods only |
| `voice` | en-US-AriaNeural | Live TTS voice (must be in the server allowlist); the fallback Windows voice uses the matching name part |
| `rate` | +8% | Live TTS speed, e.g. `%2B20%25` (= +20%) |
| `pitch` | +10Hz | Live TTS pitch, e.g. `%2B35Hz` |
| `livetts` | on | `0` = skip the server, use the Windows voice only |
| `vol` | 1 | Voice volume (0–1) |
| `tts` | on | `0` = silent, text only |
| `pos` | br | `br`, `bl`, `tr`, `tl` |
| `scale` | 1 | Size multiplier |
| `duration` | 12 | Minimum seconds on screen per fact (min 6) |
| `test` / `once` | off | `test=1` fake redemptions; `once=1` only one |

## Facts
Edit `facts/facts.js` in Notepad (instructions at the top). Facts are shuffled and she won't repeat one until she's used them all.

Live voice: `GET /tts` on the Production Center (see PRODUCTION-CENTER-SPEC.md). Her body bounces to the real loudness of the audio and the bubble types in time with it. Fallback: browser speechSynthesis (Windows voices). Character art: `gnome.webp` (original painting, cut out with `tools/cutout.py`, not Blizzard art). Font: Archivo Narrow, SIL OFL (`OFL.txt`).
