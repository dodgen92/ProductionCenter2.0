# Pandaren Counselor ("Ask the Monk")
Viewer redeems **Ask the Monk** and types a question. The monk slides in, reads "NAME asks: ..." out loud,
ponders (head tilt, tea steam speeds up, thinking dots), then speaks his answer while the bubble types along. Then he exits. Redemptions queue.

- Trigger: Production Center `GET /events` (`type:"redemption"`, reward matched case-insensitively; dedupes by `redemption_id`).
- Answer: `GET /counsel?q=&user=` -> `{"answer","source"}` (Gemini Flash-Lite on the Production Center, key stays there). If it's down: "The tea leaves are cloudy right now..." + a local saying.
- Voice: `GET /tts` with `en-HK-SamNeural`, rate -5%. Body bounces in sync with the audio. Falls back to the browser voice if `/tts` is missing.
- Animation: slide-in with petal burst, idle breathing + sway, glowing brush with golden wisps, floating tea cup with steam, audio-synced talking bounce, pondering tilt, slide-out.
- Layout: bottom-left (x 30-1020), clear of the cam frame. `?side=right` puts him at x 150-1210 (still left of the cam).

## URL params
| param | default | |
|---|---|---|
| `server` | `http://localhost:5000` | Production Center |
| `reward` | `Ask the Monk` | reward title (`rewardid=` to match by id) |
| `side` | `left` | `right` mirrors |
| `tts` | `1` | `0` = silent, text types out |
| `vol` | `1` | 0-1 |
| `voice` | `en-HK-SamNeural` | any allowlisted edge-tts voice |
| `rate` / `pitch` | `-5%` / `+0Hz` | |
| `sayname` | `1` | `0` = read only the question, not "NAME asks:" |
| `duration` | `6` | seconds the answer stays up after he finishes |
| `scale` | `1` | |
| `test` | | `1` = demo questions with canned answers (`once=1` = just one) |

Art: `art/monk.png` cut out with `tools/cutout.py`. No secrets in this folder.
