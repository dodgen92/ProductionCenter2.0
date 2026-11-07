# Fact Gnome: "Gnome Fact" channel point reward

A painted gnome scholar (pink pigtails, teal coat, glowing tome) pops up in an arcane puff, reads a random WoW fact (trivia, dev easter eggs, player legends, all in her sassy voice) out loud while it types into her speech bubble, then hops away. Redemptions queue and play one after another. Facts come from a local list, so there are no AI calls. Her voice is a pre-recorded Kokoro line when `voice/voices.js` has that fact. If it does not, she uses live neural TTS from the Production Center's `/tts` route (free `edge-tts`, no key), then a Windows voice within ~4s.

## OBS setup
1. Add a **Browser Source**, untick "Local file", URL
   `http://localhost:5000/widgets/fact-gnome/index.html?channel=remyfriend&reward=Gnome%20Fact`
2. Width 1920, height 1080; keep the default transparent CSS. Tick "Control audio via OBS" to put her voice in the mixer.
3. Preview with `&test=1` (a fake redemption every 12s). The Production Center has to be running. The page, `voice/voices.js`, and the mp3s are all served from `/widgets/`. A `file://` page cannot fetch those mp3s, so she would fall through to live TTS.

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
| `vol` | 1 | Voice trim (0–1). Still capped at 1 |
| `gain` | 1 | Linear Web Audio boost after `vol`, clamped to 0–4. Use `gain=1.6` (~+4 dB) as the starting OBS value. `gain=2.5` (~+8 dB) clips the hottest shipped line (`gnome_01.mp3` peaks around -4.4 dB). Browser `speechSynthesis` cannot take this boost |
| `tts` | on | `0` = silent, text only |
| `prerec` | on | `0` = skip the recorded lines and use live `/tts` |
| `pos` | br | `br`, `bl`, `tr`, `tl` |
| `scale` | 1 | Size multiplier |
| `duration` | 12 | Minimum seconds on screen per fact (min 6) |
| `test` / `once` | off | `test=1` fake redemptions; `once=1` only one |

## Recorded lines
`voice/voices.js` maps each exact string in `facts/facts.js` to a file under `voice/`. The shipped lines are Ed's Kokoro takes (voice `af_nicole`, sped up and pitched): `gnome_01.mp3` through `gnome_25.mp3`, one per fact, in that order. They sit around -21.5 LUFS, with the hottest peak around -4.4 dB. Leave the files at that level. The widget does not rewrite them. `gain=1.6` turns playback up without touching the mp3. `gain=2.5` is enough to clip `gnome_01.mp3`.

The key has to match the fact character for character, or that line never plays and she falls through to `/tts`. To swap one line, replace the mp3 (keeping the same name is fine) or point the existing key at a new path. Do not change the key text, and do not edit the fact in `facts.js` to match an old recording. To rebuild every line on this PC, run `python widgets/fact-gnome/tools/make_gnome_voices.py` (see the project README). That writes hash-named wavs and replaces `voices.js`. Those wavs are gitignored. The mp3s stay in the folder, but she only plays files the manifest names. Copy `voices.js` aside before a rebuild if you still want the shipped mp3s.

Fact 2's recording says "can't finish a quest chain". `facts.js` says "can't even finish". The manifest key is the `facts.js` line, so the bubble has "even" and the audio does not.

## Facts
Edit `facts/facts.js` in Notepad (instructions at the top). Facts are shuffled and she won't repeat one until she's used them all. The remaining round is saved in the browser under `gnome_deck_v1`, so an OBS refresh does not start the list over. A new fact is added to the round in progress. `?test=1` does not use that saved list. To start over, open the page once with `?resetdeck=1`.

Live voice: `GET /tts` on the Production Center (see PRODUCTION-CENTER-SPEC.md). Her body bounces to the real loudness of the audio and the bubble types in time with it. Fallback: browser speechSynthesis (Windows voices). Character art: `gnome.webp` (original painting, cut out with `tools/cutout.py`, not Blizzard art). Font: Archivo Narrow, SIL OFL (`OFL.txt`).
