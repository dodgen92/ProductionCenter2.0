# Paladin Sub Alert: grinning Forsaken paladin thanks your subs

A painted, hunched Forsaken paladin (brass goggles, gold cross, glowing sword) rises in from the bottom-left with a holy-light burst and a sword flare. He sways like a talking puppet while a parchment bubble types "Thanks for subscribing, NAME!", then drops back down. Alerts queue and never overlap. He reads chat over anonymous read-only Twitch IRC, so there's no login and no tokens.

## OBS setup
1. Add a **Browser Source**, untick "Local file", URL `file:///path/to/paladin-sub/index.html?channel=YOURNAME`.
2. Width 1920, height 1080; keep the default transparent CSS.
3. Preview anytime with `?test=1` (or `?test=1&once=1`).

(Unticking "Local file" and using a `file:///` URL is what keeps the `?params` working.)

## Sounds (random mp3 each alert)
Drop your `.mp3` files into the `sounds` folder and list their names in `sounds/sounds.js` (open it in Notepad; instructions are inside). Each time the paladin fires, one random sound plays, never the same one twice in a row. If you leave the list empty, it picks up files named `1.mp3`, `2.mp3`, and so on (up to 50). In OBS, tick **Control audio via OBS** on the browser source so the sounds show up in your mixer.

## Events (Twitch USERNOTICE `msg-id`)
| msg-id | Bubble |
|---|---|
| `sub` | Thanks for subscribing, NAME! |
| `resub` | Same, plus "N months!" in smaller text (`msg-param-cumulative-months`) |
| `submysterygift` / `anonsubmysterygift` | One alert: "N gifted subs!" / Thanks for the gifted subs, NAME! |
| `subgift` / `anonsubgift` | Thanks for the gifted subs, NAME! (skipped for ~10s after that gifter's gift bomb, so a 5-gift bomb is one alert, not six) |

## Follows (silent) + Production Center feed
Follows don't show up in chat, so they come from the Production Center feed (`GET {server}/events?since=N`, the same client as fact-gnome: `since=-1` first, then about every 1s, backing off to 15s if the server is down). An event `{"type":"follow","user":NAME}` shows **New follower!** / "Thanks for the follow, NAME!" for about 3.5s. **Follows never play a sound.** If more than 3 follows are waiting, they merge into one alert: "Thanks for the follows, A, B and 3 more!".
The feed's `sub`/`resub`/`gift`/`bits`/`raid` events are only used while IRC is disconnected, and the same type+name within 30s never plays twice. Script hook: `window.paladinSub.follow(name)`.
The backend needs EventSub `channel.follow` v2 (scope `moderator:read:followers`) published as `{type:'follow', user, login}`. See fact-gnome/PRODUCTION-CENTER-SPEC.md.

## URL params
| Param | Default | Meaning |
|---|---|---|
| `channel` / `twitch` | – | Twitch channel |
| `pos` | bl | `bl` bottom-left, `l` middle-left, `tl` top-left |
| `x`, `y` | 0 | Pixel offset |
| `scale` | 1 | Size multiplier |
| `duration` | 6 | Seconds per alert (min 4) |
| `test` | off | `1` = fake sub, resub (14 mo), gift bomb (5), raid, 500 bits and a silent follow, one every 9s, looping |
| `once` | off | With `test=1`, play one alert only |
| `vol` | 0.8 | Sound volume, 0 to 1 |
| `sound` | on | `0` = mute the sounds |
| `follows` | on | `0` = no follow alerts |
| `followdur` | 3.5 | Seconds per follow alert |
| `server` | http://localhost:5000 | Production Center URL; `0` = off (test mode skips it unless set) |

Names are sanitized (control characters and `<>&"'` stripped, max 25 characters) and inserted as text, never as HTML.

Character art: `paladin.webp` (original painting, cut out with `tools/cutout.py`, not Blizzard art). Animation is CSS transforms on the painting. Font: Archivo Narrow, SIL OFL (`OFL.txt`).
