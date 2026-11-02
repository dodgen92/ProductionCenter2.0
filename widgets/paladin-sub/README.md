# Paladin Sub Alert: grinning Forsaken paladin thanks your subs

A painted, hunched Forsaken paladin (brass goggles, gold cross, glowing sword) rises in from the bottom-left with a holy-light burst and a sword flare. He sways like a talking puppet while a parchment bubble types "Thanks for subscribing, NAME!", then drops back down. A second parchment under the bubble shows the recorded line he is speaking. Alerts queue and never overlap. He reads chat over anonymous read-only Twitch IRC, so there's no login and no tokens. The Production Center feed covers the same alerts when IRC is down, including follows (follows never show up in chat).

## OBS setup
1. Add a **Browser Source**. Leave "Local file" unticked. Either URL works:
   - `http://localhost:5000/widgets/paladin-sub/index.html?channel=YOURNAME` (Production Center has to be running)
   - `file:///path/to/paladin-sub/index.html?channel=YOURNAME`
2. Width 1920, height 1080. Leave the page transparent.
3. Preview anytime with `?test=1` (or `?test=1&once=1`).

(Unticking "Local file" and using a `file:///` URL is what keeps the `?params` working. The localhost URL keeps them too.)

## Voice lines
On each alert he plays one mp3 from `audio/` and the words from that take sit on the parchment under the chat bubble. The bubble itself is unchanged: "Thanks for subscribing, NAME!", and the same kind of line for follows, gifts, bits, and raids.

Edit the wording in `lines.js` (open it in Notepad). Change `text`. Leave `file` matched to the mp3 name. Save, then refresh the browser source. Keep the line in double quotes, and use `'` inside a line rather than `"`.

| Events | Files | How one is chosen |
|---|---|---|
| Sub, resub, gifted sub, bits | `Dono1.mp3` … `Dono11.mp3` | Random. Not the same file twice in a row. |
| Follow | `Follow1.mp3` … `Follow5.mp3` | Random. Not the same file twice in a row. |
| Raid | `Raid1.mp3` | Always this file. |

The bubble and the line stay up until the mp3 ends (`ended`). If the file fails to load, he gives up after about 6 seconds so the next alert is not stuck. There is also a 90 second cap if a clip starts and never ends. Alerts that arrive while he is talking wait. They do not play on top of each other.

`?sound=0` mutes the voice and the bed. The line text still shows, for the normal alert time. `?vol=` is the voice volume, 0 to 1, default 0.8. The bed plays at about a third of that, so the words stay on top. In OBS, tick **Control audio via OBS** so both show up in the mixer.

On a sub, resub, gift, bits, or raid, a random mp3 from `sounds/` plays under the voice line. That is the same bed the widget played before the recorded lines. A follow does not play it. If an alert has no voice line, the bed plays at full `?vol=` instead. A follow with no line stays silent.

List those files in `sounds/sounds.js`. Leave the list empty to use `sounds/1.mp3`, `sounds/2.mp3`, and so on, up to 50.

## Preview without Twitch
`?test=1` cycles a sub, a 14-month resub, a 5-gift, a raid, 500 bits, and a follow, one every 9 seconds. They queue if a voice line is still playing.

`?test=follow`, `?test=sub`, `?test=resub`, `?test=gift`, `?test=bits`, `?test=cheer` (100 bits), or `?test=raid` fires that one type. Add `&once=1` to play a single alert and stop.

With no `channel` in the URL, the page does not open IRC. It listens to `GET /events` on the Production Center instead. That is the setup for a Twitch CLI trigger. `?test=1` skips that feed unless you also set `?server=http://localhost:5000`.

To fire a real EventSub shape locally: start `twitch event websocket start-server`, set `EVENTSUB_WS_URL=ws://127.0.0.1:8080/ws`, start `python Server.py`, and open `http://localhost:5000/widgets/paladin-sub/index.html` (no `channel`). Wait until the page has loaded, then in another terminal:

```bash
twitch event trigger channel.follow --transport=websocket
twitch event trigger channel.subscribe --transport=websocket
twitch event trigger channel.subscription.gift --transport=websocket
twitch event trigger channel.subscription.message --transport=websocket
twitch event trigger channel.cheer --transport=websocket
twitch event trigger channel.raid --transport=websocket
```

The mock's sample name is easy to repeat. The widget ignores the same type and name for 30 seconds, so wait or use `?test=` for a second look. Helix subscription lines usually fail while you are on the mock. The trigger is still delivered. Clear `EVENTSUB_WS_URL` when you want real Twitch again.

## Events (Twitch USERNOTICE `msg-id`)
| msg-id | Bubble |
|---|---|
| `sub` | Thanks for subscribing, NAME! |
| `resub` | Same, plus "N months!" in smaller text (`msg-param-cumulative-months`) |
| `submysterygift` / `anonsubmysterygift` | One alert: "N gifted subs!" / Thanks for the gifted subs, NAME! |
| `subgift` / `anonsubgift` | Thanks for the gifted subs, NAME! (skipped for ~10s after that gifter's gift bomb, so a 5-gift bomb is one alert, not six) |

## Follows + Production Center feed
Follows don't show up in chat, so they come from the Production Center feed (`GET {server}/events?since=N`, the same client as fact-gnome: `since=-1` first, then about every 1s, backing off to 15s if the server is down). An event `{"type":"follow","user":NAME}` shows **New follower!** / "Thanks for the follow, NAME!" and plays a Follow line. The alert stays up until that line ends. If more than 3 follows are waiting, they merge into one alert: "Thanks for the follows, A, B and 3 more!" (one voice line for the group).
The feed's `sub`/`resub`/`gift`/`bits`/`raid` events are only used while IRC is disconnected, and the same type+name within 30s never plays twice. Script hook: `window.paladinSub.follow(name)`.
The server already subscribes to follows (`channel.follow` v2, scope `moderator:read:followers`), subs, resubs, gifted subs (`channel:read:subscriptions`), and cheers (`channel.cheer` v1, scope `bits:read`). Incoming raids are `channel.raid` v1 with `to_broadcaster_user_id` only. That subscription needs no new scope. A raid on the feed is `{type:'raid', user, login, viewers}`.

## URL params
| Param | Default | Meaning |
|---|---|---|
| `channel` / `twitch` | – | Twitch channel |
| `pos` | bl | `bl` bottom-left, `l` middle-left, `tl` top-left |
| `x`, `y` | 0 | Pixel offset |
| `scale` | 1 | Size multiplier |
| `duration` | 6 | Seconds per alert (min 4) |
| `test` | off | `1` cycles sub, resub, gift, raid, bits, and follow every 9s. Or `test=follow` / `sub` / `resub` / `gift` / `bits` / `cheer` / `raid` for one type |
| `once` | off | With `test=1`, play one alert only |
| `vol` | 0.8 | Voice volume, 0 to 1. The bed is about a third of this |
| `sound` | on | `0` = mute the voice and the bed |
| `follows` | on | `0` = no follow alerts |
| `followdur` | 3.5 | Seconds per follow alert |
| `server` | http://localhost:5000 | Production Center URL; `0` = off (test mode skips it unless set) |

Names are sanitized (control characters and `<>&"'` stripped, max 25 characters) and inserted as text, never as HTML.

Character art: `paladin.webp` (original painting, cut out with `tools/cutout.py`, not Blizzard art). Animation is CSS transforms on the painting. Font: Archivo Narrow, SIL OFL (`OFL.txt`).
