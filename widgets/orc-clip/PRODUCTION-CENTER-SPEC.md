# Orc Clip Presenter: Production Center additions

The clip event shape you proposed is fine as is:
`{id, type:'clip', reward?, user, login, clip_id, clip_url, embed_url, title, creator, broadcaster_name, duration, video_url?, thumbnail_url, voice_line, view_count?, source?, rank?}`
- `embed_url`: any `parent` you include is replaced by the widget, so you don't need to add one. `clip_id` alone is also enough.
- `duration`: seconds (float) from Helix Get Clips. The widget relies on it to know when to hide.
- `voice_line`: `/voice_lines/orc/<file>` is the fallback when `source` + `rank` do not match a line in `lines.js`. Empty string means no fallback line.
- `source`: `wow` (top World of Warcraft clips) or `twitch` (top clips across Twitch). Omit it when the clip was not tagged.
- `rank`: 1-based place in that list. 1 is the most viewed. Omit it when unknown. The widget maps WoW #1 to `WoW10.mp3` and Twitch #1 to `Twitch5.mp3`.
- `view_count`: Helix view count. The frame prints it with commas. Omit it when unknown.
- `reward`: optional. Include the reward title if you want the widget's `?reward=` filter to apply.

## NEW (required): static widget route
Twitch clip embeds refuse to play in `file://` pages (tested). The widget must be loaded from `http://localhost:5000`.

    GET /widgets/<path:p>   -> send_from_directory(r"C:\Users\tyler\Desktop\Stream-Widgets", p)

- Use `flask.send_from_directory` (or `safe_join`) so `..` traversal is impossible. Directory listing is not needed.
- Correct MIME types are needed for .html/.css/.js/.png/.webp/.mp3/.ttf (Flask's defaults are fine).
- Make it localhost-only like /events and /tts. Your ngrok guard (403 on anything but POST /webhook) already covers it.
- Optional: `Cache-Control: no-store` on this route so widget edits show up after an OBS "Refresh cache of current page".

Flask sketch:
```python
WIDGETS_DIR = r"C:\Users\tyler\Desktop\Stream-Widgets"
@app.route("/widgets/<path:p>")
def widgets(p):
    r = send_from_directory(WIDGETS_DIR, p)
    r.headers["Cache-Control"] = "no-store"
    return r
```
The existing `GET /voice_lines/orc/<file>` stays as you planned. Since the widget is then same-origin with it, it needs no CORS headers.

`broadcaster_name` = Helix clips `broadcaster_name` (the channel the clip is from). Shown in the header as "NAME: Title"; hidden if missing (`broadcaster` also accepted).

## Local clip video (preferred)
`video_url`: path to a downloaded clip MP4, either server-relative (`/clips/<file>.mp4`) or absolute (`http://localhost:5000/clips/<file>.mp4`). A bare filename is treated as `/clips/<file>`.
Route expected: `GET /clips/<file>` serving `video/mp4` (Range support recommended, CORS not required since the widget is same-origin under /widgets). Keep it blocked through ngrok like other non-webhook routes.
`duration` may be 0/missing; the widget then uses the video's real length. If `video_url` fails to load in ~8s, the widget falls back to the Twitch iframe (`embed_url`/`clip_id`) if present, else the orc says the vault is empty.
