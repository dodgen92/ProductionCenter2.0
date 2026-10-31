"""Clip library tests. No Twitch, no yt-dlp download, no network.

Read tests/README.md. These follow the same arrange / act / assert shape as test_examples.py.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

import clips
import Server


class JsonResponse:
    """Stands in for the object requests.get and requests.post return."""

    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError("helix failed")

    def json(self):
        return self._payload


class FakeYDL:
    """Stands in for yt_dlp.YoutubeDL. Writes a tiny mp4, or fails one clip on purpose."""

    urls = []

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def download(self, urls):
        FakeYDL.urls.extend(urls)
        url = urls[0]
        if "FailClip" in url:
            raise RuntimeError("yt-dlp failed")
        dest = Path(self.opts["outtmpl"].replace("%(ext)s", "mp4"))
        dest.write_bytes(b"fake-mp4")


def helix_clip(clip_id, views, **extra):
    data = {
        "id": clip_id,
        "url": f"https://clips.twitch.tv/{clip_id}",
        "embed_url": f"https://clips.twitch.tv/embed?clip={clip_id}",
        "title": extra.pop("title", clip_id),
        "broadcaster_name": extra.pop("broadcaster_name", "Durotan_Live"),
        "creator_name": extra.pop("creator_name", "Peonwork"),
        "duration": extra.pop("duration", 12.5),
        "view_count": views,
        "thumbnail_url": extra.pop("thumbnail_url", "https://example.test/thumb.jpg"),
    }
    data.update(extra)
    return data


@pytest.fixture(autouse=True)
def clean_clip_state(monkeypatch, tmp_path):
    """Each test gets an empty feed and an empty clip folder."""

    Server.EVENT_ID = 0
    Server.EVENTS.clear()
    Server._last_voice_line = None
    monkeypatch.setattr(Server, "CLIPS_DIR", tmp_path / "clips_cache")
    monkeypatch.setattr(Server, "VOICE_LINES_DIR", tmp_path / "voice_lines")
    monkeypatch.delenv("BROADCASTER_USER_ID", raising=False)
    FakeYDL.urls = []


@pytest.fixture
def client():
    Server.app.config["TESTING"] = True
    return Server.app.test_client()


def test_top_five_merges_games_and_drops_duplicate_ids():
    """The 5 highest view counts are kept, the WoW list stops at 10, and a shared id appears once."""

    # Proves: choose_library_clips does the merge the startup download uses.
    # No Helix call. The numbers below are the whole input.

    def clip(cid, views):
        return {"id": cid, "view_count": views}

    # 13 WoW clips. Only the 10 with the most views should survive.
    wow = [clip("shared", 1000)]
    for number in range(12):
        wow.append(clip(f"wow-{number}", 10 + number))

    # Spread across games, including a second copy of "shared".
    # Ranked: shared 1000, a 900, b 800, c 700, d 600, then e 500, f 400.
    games = [
        [clip("shared", 1000), clip("a", 900), clip("b", 800)],
        [clip("c", 700), clip("d", 600), clip("e", 500)],
        [clip("f", 400), clip("a", 900)],
    ]

    # Act
    chosen = clips.choose_library_clips(wow, games)

    # Assert
    ids = [item["id"] for item in chosen]
    assert len(ids) == len(set(ids))
    assert ids.count("shared") == 1
    assert "a" in ids and "b" in ids and "c" in ids and "d" in ids
    assert "e" not in ids
    assert "f" not in ids
    # shared (1000 views) plus wow-3..wow-11 is the WoW top 10. wow-2 has 12 views.
    assert "wow-11" in ids
    assert "wow-3" in ids
    assert "wow-2" not in ids
    assert len(ids) == 14


def test_library_asks_for_top_10_wow_clips_from_the_last_24_hours(monkeypatch):
    """The library asks Helix for 10 WoW clips whose started_at is 24 hours ago."""

    # Proves: game_id is World of Warcraft, first is 10, and the window is exactly one day.
    # The clock is frozen so the timestamps do not depend on when the test runs.

    calls = []

    def fake_get(url, headers=None, params=None, timeout=None):
        calls.append({"url": url, "params": dict(params or {})})
        if url.endswith("/games/top"):
            return JsonResponse({"data": [{"id": "509658", "name": "Just Chatting"}]})
        return JsonResponse({"data": []})

    monkeypatch.setattr(clips.requests, "get", fake_get)
    frozen = datetime(2026, 10, 31, 15, 0, tzinfo=timezone.utc)

    # Act
    clips.fetch_library_clips("app-token", now=frozen)

    # Assert
    wow = [item for item in calls if item["params"].get("game_id") == clips.GAME_ID]
    assert len(wow) == 1
    assert wow[0]["url"] == "https://api.twitch.tv/helix/clips"
    assert wow[0]["params"]["first"] == 10
    assert wow[0]["params"]["started_at"] == "2026-10-30T15:00:00Z"
    assert wow[0]["params"]["ended_at"] == "2026-10-31T15:00:00Z"
    assert datetime.fromisoformat(
        wow[0]["params"]["ended_at"].replace("Z", "+00:00")
    ) - datetime.fromisoformat(
        wow[0]["params"]["started_at"].replace("Z", "+00:00")
    ) == timedelta(hours=24)
    games = [item for item in calls if item["url"].endswith("/games/top")]
    assert len(games) == 1
    assert games[0]["params"]["first"] == 50
    chatting = [item for item in calls if item["params"].get("game_id") == "509658"]
    assert len(chatting) == 1
    assert chatting[0]["params"]["first"] == 10
    assert chatting[0]["params"]["started_at"] == wow[0]["params"]["started_at"]
    assert chatting[0]["params"]["ended_at"] == wow[0]["params"]["ended_at"]


def test_refresh_writes_an_index_and_skips_a_failed_download(monkeypatch, capsys):
    """Startup clears old files, downloads the rest, and writes index.json. One bad clip is skipped."""

    # Proves: the index rows match the Helix clips, a failed yt-dlp clip is not listed,
    # and the log line says how many files landed. Nothing calls the real internet.

    folder = Server.CLIPS_DIR
    folder.mkdir()
    (folder / "stale.mp4").write_bytes(b"old")
    (folder / "index.json").write_text('[{"file": "stale.mp4"}]', encoding="utf-8")
    (folder / ".gitkeep").write_text("", encoding="utf-8")

    wow_a = helix_clip(
        "WowA",
        30,
        title="Big pull",
        broadcaster_name="Durotan_Live",
        creator_name="Peonwork",
        duration=12.5,
        thumbnail_url="https://example.test/a.jpg",
    )
    wow_b = helix_clip("WowB", 20, title="Second pull")
    global_a = helix_clip("GlobalA", 900, title="Site wide", broadcaster_name="BigChannel")
    global_b = helix_clip("GlobalB", 700, title="Another")
    fail_clip = helix_clip("FailClip", 800, title="Broken download")

    def fake_post(url, params=None, timeout=None, **kwargs):
        assert url == "https://id.twitch.tv/oauth2/token"
        assert (params or {}).get("grant_type") == "client_credentials"
        return JsonResponse({"access_token": "app-token"})

    def fake_get(url, headers=None, params=None, timeout=None):
        assert headers["Authorization"] == "Bearer app-token"
        assert headers["Client-ID"] == "test-client-id"
        params = params or {}
        if url.endswith("/games/top"):
            return JsonResponse({"data": [
                {"id": "111", "name": "Just Chatting"},
                {"id": "222", "name": "Fortnite"},
                {"id": "bad", "name": "Broken"},
            ]})
        game_id = str(params.get("game_id") or "")
        if game_id == clips.GAME_ID:
            return JsonResponse({"data": [wow_a, wow_b]})
        if game_id == "111":
            return JsonResponse({"data": [global_a, wow_a]})
        if game_id == "222":
            return JsonResponse({"data": [fail_clip, global_b]})
        if game_id == "bad":
            raise requests.ConnectionError("offline")
        raise AssertionError("unexpected Helix URL")

    import yt_dlp
    monkeypatch.setattr(clips.requests, "post", fake_post)
    monkeypatch.setattr(clips.requests, "get", fake_get)
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)

    # Act
    Server.refresh_clip_library()

    # Assert: old video is gone, the placeholder stayed, the failed clip was not saved.
    assert not (folder / "stale.mp4").is_file()
    assert (folder / ".gitkeep").is_file()
    assert not (folder / "FailClip.mp4").is_file()
    assert not (folder / "index.json.tmp").exists()
    saved = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    by_id = {item["clip_id"]: item for item in saved}
    assert set(by_id) == {"WowA", "WowB", "GlobalA", "GlobalB"}
    assert by_id["WowA"] == {
        "file": "WowA.mp4",
        "clip_id": "WowA",
        "url": "https://clips.twitch.tv/WowA",
        "embed_url": "https://clips.twitch.tv/embed?clip=WowA",
        "title": "Big pull",
        "broadcaster_name": "Durotan_Live",
        "creator": "Peonwork",
        "duration": 12.5,
        "view_count": 30,
        "thumbnail_url": "https://example.test/a.jpg",
    }
    assert (folder / "WowA.mp4").is_file()
    assert all(url.startswith("https://clips.twitch.tv/") for url in FakeYDL.urls)
    assert all("app-token" not in url for url in FakeYDL.urls)
    assert "downloaded 4 clips" in capsys.readouterr().out


def test_play_a_clip_publishes_a_random_local_file(monkeypatch, tmp_path):
    """A ready library publishes video_url and the channel name, and does not call Helix."""

    # Proves: the event the orc widget reads comes from index.json.
    # One row, so the random pick is that row.

    voice = tmp_path / "voice_lines" / "orc"
    voice.mkdir(parents=True)
    (voice / "hello.mp3").write_bytes(b"not really audio")

    folder = Server.CLIPS_DIR
    folder.mkdir()
    (folder / "ClipId.mp4").write_bytes(b"not really a video")
    entry = {
        "file": "ClipId.mp4",
        "clip_id": "ClipId",
        "url": "https://clips.twitch.tv/ClipId",
        "embed_url": "https://clips.twitch.tv/embed?clip=ClipId",
        "title": "Big pull",
        "broadcaster_name": "Durotan_Live",
        "creator": "Peonwork",
        "duration": 12.5,
        "view_count": 99,
        "thumbnail_url": "https://example.test/thumb.jpg",
    }
    (folder / "index.json").write_text(json.dumps([entry]), encoding="utf-8")

    def fail_token():
        raise AssertionError("a local clip must not ask Twitch for a token")

    def fail_wow(token, hours=200, now=None):
        raise AssertionError("a local clip must not fetch the WoW list")

    monkeypatch.setattr(Server.clips, "get_app_token", fail_token)
    monkeypatch.setattr(Server.clips, "get_top_wow_clips", fail_wow)

    # Act
    Server.play_clip_for("RemyFriend", "remyfriend", "Play a Clip")

    # Assert
    assert len(Server.EVENTS) == 1
    event = Server.EVENTS[0]
    assert event["id"] == 1
    assert event["type"] == "clip"
    assert event["reward"] == "Play a Clip"
    assert event["user"] == "RemyFriend"
    assert event["login"] == "remyfriend"
    assert event["voice_line"] == "/voice_lines/orc/hello.mp3"
    assert event["clip_id"] == "ClipId"
    assert event["clip_url"] == "https://clips.twitch.tv/ClipId"
    assert event["embed_url"] == "https://clips.twitch.tv/embed?clip=ClipId"
    assert event["video_url"] == "/clips/ClipId.mp4"
    assert event["broadcaster_name"] == "Durotan_Live"
    assert event["title"] == "Big pull"
    assert event["creator"] == "Peonwork"
    assert event["duration"] == 12.5
    assert event["thumbnail_url"] == "https://example.test/thumb.jpg"


def test_play_a_clip_falls_back_to_embed_when_library_is_empty(monkeypatch, tmp_path):
    """No index yet: Play a Clip still publishes the Helix embed, including the channel name."""

    # Proves: an empty clips_cache (startup still downloading, or nothing saved)
    # uses fetch_random_clip. video_url stays blank so the widget uses the iframe.

    voice = tmp_path / "voice_lines" / "orc"
    voice.mkdir(parents=True)
    (voice / "hello.mp3").write_bytes(b"not really audio")

    def fake_token():
        return "app-token"

    def fake_wow_clips(token, hours=200, now=None):
        assert token == "app-token"
        return [{
            "id": "ClipId",
            "url": "https://clips.twitch.tv/ClipId",
            "embed_url": "https://clips.twitch.tv/embed?clip=ClipId",
            "title": "Big pull",
            "creator_name": "Someone",
            "broadcaster_name": "SomeChannel",
            "duration": 8,
            "thumbnail_url": "https://example.test/thumb.jpg",
        }]

    monkeypatch.setattr(Server.clips, "get_app_token", fake_token)
    monkeypatch.setattr(Server.clips, "get_top_wow_clips", fake_wow_clips)

    # Act
    Server.play_clip_for("RemyFriend", "remyfriend", "Play a Clip")

    # Assert
    assert len(Server.EVENTS) == 1
    event = Server.EVENTS[0]
    assert event["type"] == "clip"
    assert event["user"] == "RemyFriend"
    assert event["login"] == "remyfriend"
    assert event["reward"] == "Play a Clip"
    assert event["clip_id"] == "ClipId"
    assert event["embed_url"] == "https://clips.twitch.tv/embed?clip=ClipId"
    assert event["broadcaster_name"] == "SomeChannel"
    assert event["creator"] == "Someone"
    assert event["title"] == "Big pull"
    assert event["duration"] == 8
    assert event["video_url"] == ""
    assert event["voice_line"] == "/voice_lines/orc/hello.mp3"


def test_clips_route_supports_range_and_rejects_traversal(client, tmp_path):
    """GET /clips serves the mp4 with Range, and a .. URL cannot read a file outside the folder."""

    # Proves: video/mp4 + 206 for a byte range, 404 for a path that climbs out,
    # and 403 when a proxy forwarded the request.

    folder = Server.CLIPS_DIR
    folder.mkdir()
    payload = b"0123456789abcdef"
    (folder / "demo.mp4").write_bytes(payload)
    secret = tmp_path / "secret.txt"
    secret.write_text("top-secret", encoding="utf-8")

    # Act
    ranged = client.get("/clips/demo.mp4", headers={"Range": "bytes=0-3"})

    # Assert
    assert ranged.status_code == 206
    assert ranged.data == b"0123"
    assert ranged.mimetype == "video/mp4"
    assert ranged.headers["Content-Range"] == "bytes 0-3/16"
    assert ranged.headers["Accept-Ranges"] == "bytes"

    # Act: climb out of clips_cache toward secret.txt.
    escaped = client.get("/clips/../secret.txt")

    # Assert
    assert escaped.status_code == 404
    assert b"top-secret" not in escaped.data
    assert Server._clip_file_path("../secret.txt") is None
    assert Server._clip_file_path("..\\secret.txt") is None
    assert Server._clip_file_path("demo.mp4/../../secret.txt") is None

    # Act
    encoded = client.get("/clips/..%2fsecret.txt")

    # Assert
    assert encoded.status_code == 404
    assert b"top-secret" not in encoded.data

    # Act
    forwarded = client.get(
        "/clips/demo.mp4",
        headers={"X-Forwarded-For": "203.0.113.5"},
    )

    # Assert
    assert forwarded.status_code == 403


def test_widgets_are_served_from_the_repo_folder(client, monkeypatch):
    """With WIDGETS_DIR unset, /widgets/orc-clip comes from this repo's widgets folder."""

    # Proves: the default folder is widgets/ next to Server.py, not a path from .env.

    monkeypatch.delenv("WIDGETS_DIR", raising=False)

    # Act
    page = client.get("/widgets/orc-clip/index.html")
    style = client.get("/widgets/orc-clip/style.css")

    # Assert
    assert page.status_code == 200
    assert b"Orc Clip Presenter" in page.data
    assert page.headers["Cache-Control"] == "no-store"
    assert style.status_code == 200
    assert Server.widgets_directory() == Server.BASE_DIR / "widgets"
