import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

# Prefer TWITCH_CLIENT_SECRET. Fall back to SECRET so an older .env
# that stored the app client secret under SECRET keeps working.
GAME_ID = "18122"

# The orc's downloaded library looks at the last day.
# `python clips.py` still uses the wider window in get_top_wow_clips.
LIBRARY_HOURS = 24
WOW_TOP = 10
GLOBAL_TOP = 5
# Helix has no "top clips on all of Twitch" call. Get Clips needs a
# broadcaster, a game, or a clip id. We ask the 50 games with the most
# viewers right now (one page; Helix allows up to 100), then each game's
# recent clips, and keep the 5 highest view counts.
TOP_GAMES = 50
# One game can own several of those top 5, so take more than one clip per game.
CLIPS_PER_GAME = 10


def _client_id():
    return os.getenv("TWITCH_CLIENT_ID")


def _client_secret():
    return os.getenv("TWITCH_CLIENT_SECRET") or os.getenv("SECRET")


def get_app_token():
    """App access token (client credentials). Same call Play a Clip uses."""

    response = requests.post(
        "https://id.twitch.tv/oauth2/token",
        params={
            "client_id": _client_id(),
            "client_secret": _client_secret(),
            "grant_type": "client_credentials",
        },
        timeout=15,
    )

    response.raise_for_status()
    return response.json()["access_token"]


def _as_helix_time(moment):
    """UTC time in the shape Helix uses, such as 2026-10-30T12:00:00Z."""

    text = moment.astimezone(timezone.utc).isoformat()
    if text.endswith("+00:00"):
        text = text[:-6] + "Z"
    return text


def _helix_get(token, path, params):
    response = requests.get(
        f"https://api.twitch.tv/helix/{path}",
        headers={
            "Client-ID": _client_id(),
            "Authorization": f"Bearer {token}",
        },
        params=params,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def get_top_wow_clips(token, hours=200, now=None):
    """Most-viewed World of Warcraft clips in the last `hours` hours.

    Helix already sorts by view count, so first=10 is the top 10.
    The command-line script keeps the 200 hour window. The clip library
    passes hours=24. `now` is optional so a test can freeze the clock.
    """

    now = now or datetime.now(timezone.utc)
    started = now - timedelta(hours=hours)
    body = _helix_get(token, "clips", {
        "game_id": GAME_ID,
        "started_at": _as_helix_time(started),
        "ended_at": _as_helix_time(now),
        "first": WOW_TOP,
    })
    return body.get("data", [])


def get_broadcaster_clips(token, broadcaster_id):
    """Clips from one channel, most-viewed first. Play a Clip picks one at random.

    Dates are left off on purpose. Helix then returns the top clips by views.
    If started_at is set without ended_at, Twitch only looks one week ahead.
    """

    body = _helix_get(token, "clips", {
        "broadcaster_id": broadcaster_id,
        "first": 100,
    })
    return body.get("data", [])


def get_top_games(token, first=TOP_GAMES):
    """Games with the most viewers right now."""

    body = _helix_get(token, "games/top", {"first": first})
    return body.get("data", [])


def get_game_clips(token, game_id, started_at, ended_at, first=CLIPS_PER_GAME):
    """Most-viewed clips for one game between two times."""

    body = _helix_get(token, "clips", {
        "game_id": game_id,
        "started_at": started_at,
        "ended_at": ended_at,
        "first": first,
    })
    return body.get("data", [])


def _views(clip):
    try:
        return int(clip.get("view_count") or 0)
    except (TypeError, ValueError):
        return 0


def _clip_id(clip):
    if not isinstance(clip, dict):
        return ""
    return str(clip.get("id") or "").strip()


def _best_unique(clips, limit):
    """Highest view counts first. The same clip id is kept once."""

    ranked = sorted(
        (clip for clip in (clips or []) if isinstance(clip, dict)),
        key=_views,
        reverse=True,
    )
    picked = []
    seen = set()
    for clip in ranked:
        cid = _clip_id(clip)
        if not cid or cid in seen:
            continue
        seen.add(cid)
        picked.append(clip)
        if len(picked) >= limit:
            break
    return picked


def choose_library_clips(wow_clips, game_clip_groups, wow_limit=WOW_TOP, global_limit=GLOBAL_TOP):
    """WoW's top clips, plus the top clips from the game lists, with no repeat ids.

    A clip that is in both lists is downloaded once. It still counts as one of
    the global top, so the library can be a little smaller than 15.
    """

    wow_picked = _best_unique(wow_clips, wow_limit)
    flat = []
    for group in game_clip_groups or []:
        if isinstance(group, dict):
            flat.append(group)
        else:
            flat.extend(group or [])
    global_picked = _best_unique(flat, global_limit)

    chosen = []
    seen = set()
    for clip in wow_picked + global_picked:
        cid = _clip_id(clip)
        if not cid or cid in seen:
            continue
        seen.add(cid)
        chosen.append(clip)
    return chosen


def fetch_library_clips(token, now=None):
    """The clips we want on disk: 10 WoW clips and 5 from the top games.

    One game's request can fail. The others are still used. `now` is optional
    so a test can freeze the clock.
    """

    now = now or datetime.now(timezone.utc)
    started_at = _as_helix_time(now - timedelta(hours=LIBRARY_HOURS))
    ended_at = _as_helix_time(now)

    try:
        wow = get_top_wow_clips(token, hours=LIBRARY_HOURS, now=now)
    except Exception as exc:
        print(f"[clips] WARNING: WoW clips failed ({type(exc).__name__}).")
        wow = []

    try:
        games = get_top_games(token, first=TOP_GAMES)
    except Exception as exc:
        print(f"[clips] WARNING: top games failed ({type(exc).__name__}).")
        games = []

    groups = []
    for game in games:
        if not isinstance(game, dict):
            continue
        game_id = str(game.get("id") or "").strip()
        if not game_id:
            continue
        try:
            groups.append(get_game_clips(
                token,
                game_id,
                started_at,
                ended_at,
                first=CLIPS_PER_GAME,
            ))
        except Exception as exc:
            print(f"[clips] WARNING: skipped game {game_id} ({type(exc).__name__}).")
    return choose_library_clips(wow, groups)


def clip_mp4_name(clip_id):
    """A safe file name. Twitch clip ids are letters, numbers, and dashes."""

    safe = re.sub(r"[^A-Za-z0-9_-]+", "", str(clip_id or ""))
    if not safe:
        return ""
    return safe + ".mp4"


def index_entry(clip, filename):
    """One row of clips_cache/index.json."""

    duration = clip.get("duration")
    if duration is None:
        duration = 0
    return {
        "file": filename,
        "clip_id": _clip_id(clip),
        "url": clip.get("url") or "",
        "embed_url": clip.get("embed_url") or "",
        "title": clip.get("title") or "",
        "broadcaster_name": clip.get("broadcaster_name") or "",
        "creator": clip.get("creator_name") or clip.get("creator") or "",
        "duration": duration,
        "view_count": _views(clip),
        "thumbnail_url": clip.get("thumbnail_url") or "",
    }


def write_clip_index(folder, entries):
    """Write index.json next to the mp4 files. Replace is one step, so a reader never sees a half file."""

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    temp = folder / "index.json.tmp"
    temp.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    temp.replace(folder / "index.json")


def download_clip_mp4(url, dest_file):
    """Save one public clip URL as an mp4. Raises if the file is not there afterward.

    The app token is not sent to yt-dlp. The clip page is public.
    """

    import yt_dlp

    dest_file = Path(dest_file)
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    if dest_file.exists():
        dest_file.unlink()
    # outtmpl adds the real extension. We only keep the file when it is .mp4.
    options = {
        "format": "best[ext=mp4]/mp4/best",
        "outtmpl": str(dest_file.with_suffix("")) + ".%(ext)s",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.download([url])
    if dest_file.is_file():
        return
    # A different container (webm, for example) is not what the widget plays.
    for extra in dest_file.parent.glob(dest_file.stem + ".*"):
        try:
            extra.unlink()
        except OSError:
            pass
    raise RuntimeError("yt-dlp did not write an mp4")


def build_clip_library(token, folder, now=None):
    """Download the library into `folder` and write index.json.

    A clip that fails to download is skipped. The others are still indexed.
    Returns the index rows.
    """

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    chosen = fetch_library_clips(token, now=now)
    entries = []
    for clip in chosen:
        clip_id = _clip_id(clip)
        filename = clip_mp4_name(clip_id)
        url = clip.get("url") or ""
        if not filename or not url:
            print(f"[clips] WARNING: skipped clip {clip_id or '(no id)'} (no url).")
            continue
        dest = folder / filename
        try:
            download_clip_mp4(url, dest)
        except Exception as exc:
            print(f"[clips] WARNING: skipped clip {clip_id} ({type(exc).__name__}).")
            if dest.exists():
                try:
                    dest.unlink()
                except OSError:
                    pass
            continue
        entries.append(index_entry(clip, filename))
    write_clip_index(folder, entries)
    return entries


if __name__ == "__main__":
    token = get_app_token()

    clips = get_top_wow_clips(token)

    print(f"Found {len(clips)} WoW clips:\n")

    for i, clip in enumerate(clips, 1):
        print(f"{i}. {clip['title']}")
        print(f"   Creator: {clip['creator_name']}")
        print(f"   Views: {clip['view_count']:,}")
        print(f"   URL: {clip['url']}")
        print()
