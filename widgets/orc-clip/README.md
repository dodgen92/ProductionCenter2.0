# Orc Clip Presenter

"Play a Clip" channel point reward: the orc scholar pops in, plays the recorded line for that clip's rank, then a Twitch clip plays in a gold WoW-style frame (title, rank, view count, "clipped by", "redeemed by"), then everything hides. Redemptions queue and play one after another.

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
| side | left | `right` moves the orc to the right. The frame stays where the CSS variables put it, so it does not jump onto the webcam |
| vvol | 0.9 | voice line trim, 0-1. Not the clip. Still capped at 1 |
| cvol | 0.8 | clip `<video>` trim, 0 to 1. `CVOL` in `orc.js`. Still capped at 1 |
| gain | 1 | Linear Web Audio boost after `vvol` and `cvol`, clamped to 0–4. Put `gain=1.6` in the OBS URL for the starting lift (~+4 dB). `gain=2.5` (~+8 dB) drives the shipped voice files past full scale and can crunch the peaks. It does not turn up the Twitch iframe, and a cross-origin clip file stays at `cvol` |
| muted | 0 | `1` = start the clip muted |
| parent | page hostname over http, else `localhost` | comma list allowed |
| maxdur | 60 | cap in seconds on how long a clip is shown |
| buffer | 5 | seconds added to `duration` for the embed to load and start |
| scale | 1 | scale the whole layout |
| framex, framey | 10, 10 | frame position in pixels. Same as `--frame-left` and `--frame-top` in `style.css` |
| framew, frameh | 1450, 920 | frame size in pixels. Same as `--frame-width` and `--frame-height`. The video stays 16:9 inside that box |
| test | | `1` = the old fake cycle (voice line `test/voice-test.mp3` plus a real public clip). `wow` or `twitch` previews one rank, for example `?test=wow&rank=3` or `?test=twitch&rank=1` (local test clip, 12,345 views). `&once=1` plays one. `&clip=SLUG` uses your own clip with `test=1` |

## Behaviour
- The server picks the clip from a shuffle bag (`clips_cache/shuffle.json`), one whole library, not separate WoW and Twitch bags. Nothing repeats until every downloaded file has played. A new download joins the current round. Delete `shuffle.json` to start over. `?test=` and `?rank=` are previews and do not use the bag.
- A ranked line (see Voice lines) holds the clip on its first frame, or on the thumbnail if the file is not ready. A film countdown inside the clip window runs for that line's `voice_end_s` and hits 0 when the orc stops talking. Then the clip starts and the orc slides off toward the side he is standing on (`side=left` goes left and down, `side=right` goes right and down). The next clip walks him back in. The music tail fades out quickly so it does not sit on the clip audio. If the mp3 ends first, the clip starts then.
- A clip with no matching line still waits until `voice_line` finishes (or a 20 s cap), then plays. That is the old path.
- No voice line: the orc shows for about 1.4 s, then the clip plays.
- No clip: the orc says "No clips in the vault yet" (with his voice line if there is one) and leaves.
- Clip end: Twitch's clip embed has no JS API or postMessage events (checked: zero messages from the iframe). So the widget uses `duration + buffer` (capped by maxdur), with a gold progress bar under the clip.
- Layout rule: nothing may overlap the clip iframe, not even a drop-shadow, and no ancestor may be hidden or scaled when it loads. Otherwise Twitch logs "Autoplay disabled ... style visibility" and the clip sits paused. The countdown is removed before the iframe is created. On the old path the frame is shown first and the iframe is loaded 750 ms later. On a ranked line the frame has already been up for the whole voice, so the iframe loads once the countdown is gone.

## Voice lines
The ranked takes live in `audio/`, with the words and timing in `lines.js`. Edit `text` in Notepad. Leave `file` matched to the mp3. Save, then refresh the browser source. Keep the line in double quotes, and use `'` inside a line rather than `"`.

| Clip | Files | Which line plays |
|---|---|---|
| Top 10 World of Warcraft clips | `WoW1.mp3` … `WoW10.mp3` | WoW #1 plays `WoW10.mp3`. WoW #10 plays `WoW1.mp3`. |
| Top 5 clips across Twitch | `Twitch1.mp3` … `Twitch5.mp3` | Twitch #1 plays `Twitch5.mp3`. Twitch #5 plays `Twitch1.mp3`. |

The server sends `source` (`wow` or `twitch`) and `rank` (1 is the most viewed in that list). The widget looks those up in `lines.js`. `voice_start_s` and `voice_end_s` are seconds from the start of the file: the music starts, then the orc talks, then the music fades. The countdown length is `voice_end_s`.

If the rank has no line (11th WoW clip, a missing file, or an older library row with no rank), the widget uses `voice_line` from the server instead. That is still a random file from `voice_lines/orc/`, sent as `/voice_lines/orc/<file>`, a full URL, or a bare filename. With no file there either, he stands quietly, then the clip plays.

## Files
index.html, style.css, orc.js, lines.js, audio/ (the ranked mp3s), art/orc.png (cut out from the approved orc scholar with tools/cutout.py), test/voice-test.mp3 (test only), tools/ (cutout, mock server, headless tests).

## Music
The bed under the voice is taiko / war drums: "Taiko Drum Sequence for Looping (The Sacrifice)" by Infinita08, Freesound id 459561 (CC0). The source file was named taiko_459561. Infinita08 notes the sequence was built from a free taiko sample library. https://freesound.org/people/Infinita08/sounds/459561/

## Clip channel name
The header shows "CHANNEL: Title" (event field `broadcaster_name`, fallback `broadcaster`); just the title if missing. Long titles shrink, then ellipsize.

## Local clip videos (no more mute)
If the event has `video_url` (e.g. `/clips/x.mp4`, resolved against `server`), the clip plays in a normal <video> with sound, then hides when it ends (safety cap = duration or real length + `buffer`, max `maxdur`). Params: `cvol` (clip trim 0-1, default 0.8) and `gain` (boost, default 1). `muted=1` still mutes. A same-origin mp4 can take `gain`. A cross-origin file plays at `cvol` only. If that shared video element has already played a same-origin clip, a later cross-origin file is skipped so it does not go silent inside Web Audio, and the iframe below can play. If the file fails, it falls back to the Twitch iframe below. The iframe has no volume control and ignores `gain`.

## Clip audio (iframe fallback only)
Twitch clips only have an iframe embed (no JS player API: Twitch.Player accepts only channel/video/collection, and player.twitch.tv/?clip= errors). The embed asks for sound (`muted=false`), but Twitch's player mutes itself if the browser blocks sound autoplay. If clips play muted in OBS: right-click the source > Interact, click the clip once to unmute; that lasts for the OBS session. Also check the source isn't muted in OBS's Audio Mixer and "Control audio via OBS" is set how you want.
