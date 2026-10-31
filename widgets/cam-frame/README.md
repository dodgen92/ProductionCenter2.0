# Cam Frame (WoW-style reactive webcam frame)
Original gold-trimmed fantasy frame around a transparent cam window, with a STREAM LEVEL XP bar underneath that doubles as the alert bar. Every stream starts at Level 1; every interaction gives XP and you see how high the stream gets. A round gold level badge sits on the bar's left end, inside the frame's bounds so cropping the source can't cut it off. Standalone: anonymous Twitch IRC, no tokens.

## OBS setup
1. Add a Browser source, untick "Local file", size 1920x1080.
2. URL: file:///PATH/TO/cam-frame/index.html?channel=YOURNAME
3. Put your webcam source under it, lined up with the window (default 1280x720 centered).

## Params
| Param | Default | What |
|---|---|---|
| `channel` | – | Twitch channel (required live) |
| `base` | 100 | XP to go from level N to N+1 = base × N (L1→2 100, L2→3 200…) |
| `growth` | linear | `linear` (base×N), `flat` (always base), `exp` (base×1.5^(N-1)) |
| `xpfollow` | 10 | XP per follow |
| `xpsub` | 50 | XP per sub (also default for resub/gift) |
| `xpresub` | 50 | XP per resub |
| `xpgift` | 50 | XP per gifted sub (gift bomb of N = 50×N) |
| `xpbits` | 0.1 | XP per bit (100 bits = 10 XP) |
| `xpraid` | 2 | XP per raider |
| `xpraidmin` | 20 | minimum XP for any raid |
| `xpchat` | 0 (off) | XP per chat message, max once per user per 60s (no alert, small pop) |
| `resetafter` | 6 | hours of no XP/page load before it auto-resets to Level 1 (new stream) |
| `reset` | – | `1` forces Level 1 (remove after one load) |
| `badge` | 1 | `0` hides the level badge |
| `shape` | 16x9 | `16x9`, `1x1`, `9x16` |
| `w`, `x`, `y` | centered 1280 | cam window width and top-left (px) |
| `ws` | – | optional `ws://localhost:PORT/path` for follow events |
| `test` | – | `1` cycles fake events, starts Level 1 with base 20, never saves |

## XP (defaults)
| Event | XP | Alert |
|---|---|---|
| Follow | 10 | "NAME followed!" + shimmer |
| Sub | 50 | "NAME subscribed!" + light column |
| Resub | 50 | "NAME resubbed × N months" + light column |
| Gift sub / bomb | 50 each | gift boxes + confetti, one alert per bomb |
| Bits | 1 per 10 bits | item-quality gem (gray/white/green 100+/blue 500+/purple 1000+/orange 5000+) |
| Raid | 2 per raider, min 20 | silhouette crowd + "NAME raids with N!" |
| Chat (off) | 1 if `xpchat=1` | none |
Every alert shows "+N XP"; overflow carries into the next level. Each stream level reached plays the big gold "★ LEVEL UP! Stream Level N! ★" (several level-ups at once play one after another) and the badge pops. Alerts queue and never overlap. Tips aren't supported.

## Persistence
Level + XP are saved in localStorage per channel, so an OBS refresh mid-stream keeps progress. If more than `resetafter` hours pass with no XP and no page load, the next load starts at Level 1. The bar always shows the current level, so at the end of stream the badge and "Stream Level N" show your final level.

## Follow hook
- JS: `window.camFrame.follow('NAME')` or `window.camFrame.trigger({type:'follow', user:'NAME'})`
- WebSocket (`?ws=`): one JSON text message per event, exactly:
  `{"type":"follow","user":"NAME"}`
  Names are sanitized (max 25 chars, no markup). Unknown types are ignored.

### Spec for Production Center Manager
Subscribe to Twitch EventSub `channel.follow` version 2 (condition: broadcaster_user_id + moderator_user_id, scope moderator:read:followers). For each notification, take `event.user_name` and push `{"type":"follow","user":"<user_name>"}` as a text frame to every client connected on a local websocket (e.g. ws://localhost:PORT/camframe). The cam frame connects with `&ws=ws://localhost:PORT/camframe` and needs no tokens itself.
