# Night Elf Translator

Tyler's nerdy night elf (glasses, moon tome, little flag pins for her languages) slides in from the side and translates
channel point redemptions, then reads the translation out loud in a native neural voice. Flirty-nerdy, and a little bit into Remy.

## Rewards (create both with "Require viewer to enter text")
| Reward (default name) | Viewer types | She shows / says |
|---|---|---|
| `Translate to English` | anything in a language she knows; optional tag for romaji or short words: `jp: konnichiwa`, `ko: annyeong`, `fr: bonjour`, or a flag emoji first (tag needs `:` or `-`, so `es un buen día` still auto-detects) | original + its flag, English translation (Sonia voice) |
| `Translate from English` | `language: text` | English original, translation + flag, spoken in that language |

"From English" input formats (case-insensitive): `spanish: hello chat`, `es hello chat`, `jp: gg`, `🇫🇷 bonjour`, `to dutch: hi`,
`KOREAN - nice`, `hello chat in german`. No/unknown language -> "Which language, darling?" plus the list; the backend is not called.

Languages and voices: Spanish (Mexico flag, es-MX-DaliaNeural), Portuguese (Brazil, pt-BR-FranciscaNeural), French (fr-FR-DeniseNeural),
Japanese (ja-JP-NanamiNeural), Korean (ko-KR-SunHiNeural), Chinese Simplified (zh-CN-XiaoxiaoNeural), Chinese Traditional (gold "繁" badge,
zh-TW-HsiaoChenNeural), German (de-DE-KatjaNeural), Dutch (nl-NL-ColetteNeural), English (en-GB-SoniaNeural, rate -8%, pitch -4Hz; override with `envoice`, `enrate`, `enpitch`).
Aliases: spanish/español/es/sp/mx, portuguese/pt/br/pt-br, french/fr, japanese/ja/jp, korean/ko/kr, chinese/mandarin/zh/cn/simplified,
traditional/zh-tw/tw/繁體, german/deutsch/de, dutch/nederlands/nl, and flag emoji (🇲🇽🇪🇸🇧🇷🇵🇹🇫🇷🇯🇵🇰🇷🇨🇳🇹🇼🇩🇪🇳🇱...).

## URL params
| Param | Default | |
|---|---|---|
| `server` | `http://localhost:5000` | Production Center |
| `rewardto` / `rewardfrom` | `Translate to English` / `Translate from English` | reward titles (case-insensitive) |
| `rewardtoid` / `rewardfromid` | | match by reward id instead |
| `side` | `left` | `left` (bottom-left) or `right` |
| `tts` | on | `tts=0` = silent, text only |
| `vol` | `1` | 0..1 |
| `duration` | `9` | min seconds on screen |
| `scale` | `1` | size |
| `test` | | `test=1` cycles fake redemptions every 14 s (`once=1` = one) |

## Behavior
- Queue (max 20), input clipped to 200 chars, each redemption shown once (dedupe by redemption id).
- Polls `GET /events?since=-1` once (skip backlog), then every ~1 s; backs off to 15 s if the server is down.
- `GET /translate` (8 s timeout). On failure: "My tome is closed right now..." and the queue keeps going.
- Voice: `GET /tts` with the per-language voice, lip-sync bounce from real audio loudness. If /tts fails she uses a Windows voice
  for that language if one is installed, else the text just types out.
- Viewer text is always inserted as text, never HTML.

## Files
`index.html`, `style.css`, `translator.js`, `art/elf.png` (cutout of Tyler's approved art, `tools/cutout.py` rebuilds it),
`ArchivoNarrow.ttf` + `OFL.txt`, `preview.png`, `PRODUCTION-CENTER-SPEC.md` (the `/translate` route + voice allowlist).
