# WoW In-Game Chat Overlay (Twitch)

Reads your Twitch chat directly over anonymous, read-only Twitch IRC (`wss://irc-ws.chat.twitch.tv:443`, nick `justinfanNNNNN`). No backend, no tokens, no login.

## OBS setup
1. Add a **Browser Source** → Local file → `index.html`, then add `?channel=YOURNAME` (untick "Local file" and use `file:///path/to/wow-chat/index.html?channel=YOURNAME` so the parameter sticks).
2. Width 1920, height 1080; keep OBS's default transparent CSS.
3. Preview without going live with `?test=1`.

## URL params
| Param | Default | Meaning |
|---|---|---|
| `channel` (alias `twitch`) | required | Twitch channel to read. If it's missing, a small hint appears in the panel |
| `x`,`y`,`w`,`h` | 20, (bottom 110), 540, 240 | Panel position/size in px. `y` = top offset; without it the panel sits bottom-left |
| `size` | 16 | Font size px |
| `opacity` | 0.85 | Panel opacity |
| `tab1`,`tab2` | General, Combat Log | Tab labels |
| `fade` | 30 | Seconds before lines fade (0 = never) |
| `max` | 12 | Max lines |
| `ts` | off | `1` shows `[HH:MM]` |
| `hidecmds` | off | `1` hides messages starting with `!` |
| `hidebots` | nightbot,streamelements | Comma list of logins to hide (empty = none) |
| `test` | off | `1` = fake chat, no connection |

## Line formats
| Who | Format | Color |
|---|---|---|
| Broadcaster | `[Raid Leader] [Name]: msg` | #FF7F1A |
| Moderator | `[Officer] [Name]: msg` | #40C040 |
| VIP | `[Party] [Name]: msg` | #AAAAFF |
| Sub/founder | `[Guild] [Name]: msg` | #40FF40 |
| First-time chatter | `[Name] whispers: msg` | #FF80FF |
| Other viewers (stable hash of username) | `[Name] says: msg` / `[1. General] [Name]: msg` | #FFFFFF / #FFC0C0 |
| /me | `Name dances…` | #FF7F50 |
| Highlighted / channel-point reward | keeps role prefix | #FF80FF |
| Bits cheer | `Name receives loot: [500 Bits]. msg` | epic purple #A335EE |
| Sub/resub/gift/mystery gift/raid | system line | #FFFF00 |

Moderation: CLEARCHAT (whole chat, or one user via `target-user-id`) and CLEARMSG (`target-msg-id`) remove lines live. Emotes render from the `emotes` tag. All text is HTML-escaped.

## Limits
Anonymous chat can't see follows, channel-point redemptions without a message, or bits/follow alerts. The only extras it gets are cheers (the `bits` tag on PRIVMSG) and USERNOTICE subs and raids. The widget reconnects with backoff (1s doubling to 30s) and answers PING with PONG and RECONNECT with a reconnect.

Font: Archivo Narrow (SIL OFL, `ArchivoNarrow.ttf` + `OFL.txt`), bundled locally, with fallback `'Arial Narrow', sans-serif`.
