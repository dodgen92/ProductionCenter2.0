# Orc Clip Presenter

"Play a Clip" channel point reward: the orc scholar pops in, plays one of Tyler's recorded voice lines, then a Twitch clip plays in a gold WoW-style frame (title, "clipped by", "redeemed by"), then everything hides. Redemptions queue and play one after another.

## IMPORTANT: load it over http://localhost, not file://
Twitch clip embeds only play inside a page whose hostname matches `parent=`. Twitch enforces this with a CSP header (`frame-ancestors http://localhost:* https://localhost:*` when parent=localhost).
A `file://` page has no hostname, so the clip is always refused ("clips.twitch.tv refused to connect"), whatever parent you pass. This was tested in Chrome, and OBS's browser (CEF/Chromium) enforces the same rule.
So the Production Center serves the widget folder (see PRODUCTION-CENTER-SPEC.md), and OBS loads:

    http://localhost:5000/widgets/orc-clip/index.html

Use the word `localhost` in the URL, not 127.0.0.1. Otherwise set `&parent=127.0.0.1`.

## URL params
| param | default | |
|---|---|---|
| server | http://localhost:5000 | Production Center (`0` = off) |
| reward | Play a Clip | if the event carries `reward`, it must match (case-insensitive). Events without `reward` always fire |
| side | left | `right` = clip frame on the left, orc on its right (both stay clear of the cam at x1240-1880, y600-960) |
| vvol | 0.9 | voice line volume 0-1 |
| muted | 0 | `1` = start the clip muted |
| parent | page hostname over http, else `localhost` | comma list allowed |
| maxdur | 60 | cap in seconds on how long a clip is shown |
| buffer | 5 | seconds added to `duration` for the embed to load and start |
| scale | 1 | scale the whole layout |
| test | | `1` = fake events (voice line `test/voice-test.mp3` plus a real public clip). `&once=1` plays one. `&clip=SLUG` uses your own clip |

## Behaviour
- Voice line finishes (or a 20 s cap passes) before the clip iframe is even created, so the two never overlap.
- No voice line: the orc shows for about 1.4 s, then the clip plays.
- No clip: the orc says "No clips in the vault yet" (with his voice line if there is one) and leaves.
- Clip end: Twitch's clip embed has no JS API or postMessage events (checked: zero messages from the iframe). So the widget uses `duration + buffer` (capped by maxdur), with a gold progress bar under the clip.
- Layout rule: nothing may overlap the clip iframe, not even a drop-shadow, and no ancestor may be hidden or scaled when it loads. Otherwise Twitch logs "Autoplay disabled ... style visibility" and the clip sits paused. The frame is shown first and the iframe is loaded 750 ms later.

## Voice lines
Drop mp3s in the Production Center's `voice_lines/orc/`. The backend picks one at random (never the same twice in a row) and sends `voice_line` as `/voice_lines/orc/<file>`, a full URL, or a bare filename. All three work.

## Files
index.html, style.css, orc.js, art/orc.png (cut out from the approved orc scholar with tools/cutout.py), test/voice-test.mp3 (test only), tools/ (cutout, mock server, headless tests).

## Clip channel name
The header shows "CHANNEL: Title" (event field `broadcaster_name`, fallback `broadcaster`); just the title if missing. Long titles shrink, then ellipsize.

## Local clip videos (no more mute)
If the event has `video_url` (e.g. `/clips/x.mp4`, resolved against `server`), the clip plays in a normal <video> with sound, then hides when it ends (safety cap = duration or real length + `buffer`, max `maxdur`). Params: `cvol` (clip volume 0-1, default 1), `muted=1` still mutes. If the file fails, it falls back to the Twitch iframe below.

## Clip audio (iframe fallback only)
Twitch clips only have an iframe embed (no JS player API: Twitch.Player accepts only channel/video/collection, and player.twitch.tv/?clip= errors). The embed asks for sound (`muted=false`), but Twitch's player mutes itself if the browser blocks sound autoplay. If clips play muted in OBS: right-click the source > Interact, click the clip once to unmute; that lasts for the OBS session. Also check the source isn't muted in OBS's Audio Mixer and "Control audio via OBS" is set how you want.
