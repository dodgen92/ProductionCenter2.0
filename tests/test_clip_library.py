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
    Server._clips_downloading = False
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

    # clips.py asks Helix with APP_CLIENT_ID. TWITCH_CLIENT_ID is the user
    # token for EventSub, and this test must not depend on that name.
    monkeypatch.setenv("APP_CLIENT_ID", "test-app-client-id")

    def fake_post(url, params=None, timeout=None, **kwargs):
        assert url == "https://id.twitch.tv/oauth2/token"
        assert (params or {}).get("grant_type") == "client_credentials"
        return JsonResponse({"access_token": "app-token"})

    def fake_get(url, headers=None, params=None, timeout=None):
        assert headers["Authorization"] == "Bearer app-token"
        assert headers["Client-ID"] == "test-app-client-id"
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
        "source": "wow",
        "rank": 1,
        "thumbnail_url": "https://example.test/a.jpg",
    }
    # FailClip was Twitch #2 and did not download. GlobalB stays #3.
    assert by_id["WowB"]["source"] == "wow"
    assert by_id["WowB"]["rank"] == 2
    assert by_id["GlobalA"]["source"] == "twitch"
    assert by_id["GlobalA"]["rank"] == 1
    assert by_id["GlobalB"]["source"] == "twitch"
    assert by_id["GlobalB"]["rank"] == 3
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
        "source": "twitch",
        "rank": 2,
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
    assert event["view_count"] == 99
    assert event["source"] == "twitch"
    assert event["rank"] == 2


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
    # One clip in the fake list, and Helix puts the most-viewed clip first.
    assert event["source"] == "wow"
    assert event["rank"] == 1
    assert "view_count" not in event


def test_play_a_clip_logs_when_the_file_is_not_downloaded_yet(capsys, monkeypatch):
    """A redeem during the download, before any mp4 is saved, says so and uses the embed."""

    # Proves: we do not hand the widget a video_url for a file that is not
    # on disk yet. The log line is the one to look for in the server window.

    Server._clips_downloading = True

    def fake_token():
        return "app-token"

    def fake_wow_clips(token, hours=200, now=None):
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
    assert "[Server] clip not downloaded yet" in capsys.readouterr().out
    event = Server.EVENTS[0]
    assert event["video_url"] == ""
    assert event["embed_url"] == "https://clips.twitch.tv/embed?clip=ClipId"


def test_play_a_clip_uses_a_finished_file_while_download_continues(capsys, monkeypatch):
    """Once one mp4 is saved, a redeem plays that file instead of waiting."""

    # Proves: the index can hold finished files while _clips_downloading is
    # still true. Those files are used, and the "not downloaded yet" line
    # is not printed.

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
        "source": "twitch",
        "rank": 2,
        "thumbnail_url": "https://example.test/thumb.jpg",
    }
    (folder / "index.json").write_text(json.dumps([entry]), encoding="utf-8")
    Server._clips_downloading = True

    def fail_token():
        raise AssertionError("a saved clip must not ask Twitch for a token")

    monkeypatch.setattr(Server.clips, "get_app_token", fail_token)

    # Act
    Server.play_clip_for("RemyFriend", "remyfriend", "Play a Clip")

    # Assert
    assert "[Server] clip not downloaded yet" not in capsys.readouterr().out
    assert Server.EVENTS[0]["video_url"] == "/clips/ClipId.mp4"
    assert Server.EVENTS[0]["embed_url"] == "https://clips.twitch.tv/embed?clip=ClipId"


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


def test_library_ranks_wow_and_twitch_separately():
    """WoW #1 is the most-viewed WoW clip. A clip in both lists keeps the WoW rank.

    The shared clip still occupies its place in the Twitch list, so the next
    Twitch clip does not move up to that number.
    """

    # Proves: rank is the place in each fetched list, not a recount after deduping.

    wow = [
        {"id": "wow-low", "view_count": 10},
        {"id": "shared", "view_count": 500},
        {"id": "wow-mid", "view_count": 400},
    ]
    games = [[
        {"id": "global-top", "view_count": 900},
        {"id": "shared", "view_count": 500},
        {"id": "global-low", "view_count": 50},
    ]]

    # Act
    chosen = clips.choose_library_clips(wow, games)

    # Assert
    by_id = {item["id"]: item for item in chosen}
    assert by_id["shared"]["source"] == "wow"
    assert by_id["shared"]["rank"] == 1
    assert by_id["wow-mid"]["source"] == "wow"
    assert by_id["wow-mid"]["rank"] == 2
    assert by_id["wow-low"]["rank"] == 3
    assert by_id["global-top"]["source"] == "twitch"
    assert by_id["global-top"]["rank"] == 1
    # shared would have been Twitch #2. global-low stays Twitch #3.
    assert by_id["global-low"]["source"] == "twitch"
    assert by_id["global-low"]["rank"] == 3


def test_fallback_clip_uses_its_place_in_the_wow_list(monkeypatch):
    """Picking the second Helix clip marks it WoW #2."""

    # Proves: the embed fallback still has a rank, taken from the list order.
    # Helix puts the most-viewed clip first. No download, no network.

    def fake_token():
        return "app-token"

    def fake_wow(token, hours=200, now=None):
        assert token == "app-token"
        return [
            helix_clip("Top", 100, title="First"),
            helix_clip("Second", 40, title="Second"),
        ]

    monkeypatch.setattr(Server.clips, "get_app_token", fake_token)
    monkeypatch.setattr(Server.clips, "get_top_wow_clips", fake_wow)
    monkeypatch.setattr(Server.random, "randrange", lambda n: 1)

    # Act
    clip = Server.fetch_random_clip()

    # Assert
    assert clip["id"] == "Second"
    assert clip["source"] == "wow"
    assert clip["rank"] == 2
    assert clip["view_count"] == 40


def test_clip_event_skips_rank_when_the_row_has_none():
    """An older index row still plays. Rank is left off so the widget uses voice_line."""

    # Proves: a library built before ranks existed does not get a made-up rank.

    # Act
    fields = Server.clip_event_fields({
        "file": "demo.mp4",
        "title": "Old row",
        "view_count": 12,
    })

    # Assert
    assert fields["video_url"] == "/clips/demo.mp4"
    assert fields["view_count"] == 12
    assert fields["title"] == "Old row"
    assert "source" not in fields
    assert "rank" not in fields


def keep_order(items):
    """Stand-in for random.shuffle that leaves the list as it was."""


def test_clip_bag_plays_every_file_once_before_a_repeat(monkeypatch):
    """Three clips come out as three different files. The next round does not start with the last one."""

    # Proves: a round covers the whole library, and the reshuffle does not
    # hand back the clip that closed the previous round.

    monkeypatch.setattr(Server.random, "shuffle", keep_order)
    entries = [{"file": "a.mp4"}, {"file": "b.mp4"}, {"file": "c.mp4"}]
    state = Server._empty_shuffle()
    played = []
    for _ in range(3):
        pick, state = Server.next_from_bag(entries, state)
        played.append(pick["file"])

    assert played == ["c.mp4", "b.mp4", "a.mp4"]
    assert len(set(played)) == 3

    # Act: the round is empty, so this is the first clip of the next round.
    again, state = Server.next_from_bag(entries, state)

    # Assert: last clip was a.mp4, so the new round must not open with it.
    assert again["file"] != "a.mp4"
    assert again["file"] == "c.mp4"
    assert state["last"] == "c.mp4"

    # The shuffled list would have opened on a.mp4, which just played.
    # The bag swaps that with the other end so the new round starts somewhere else.
    forced = [{"file": "b.mp4"}, {"file": "a.mp4"}]
    parked = {"deck": [], "last": "a.mp4", "pool": ["b.mp4", "a.mp4"]}
    opened, _state = Server.next_from_bag(forced, parked)
    assert opened["file"] == "b.mp4"


def test_clip_bag_adds_a_new_file_and_drops_a_deleted_one(monkeypatch):
    """A download joins the round already in progress. A missing file is not drawn."""

    monkeypatch.setattr(Server.random, "shuffle", keep_order)
    entries = [{"file": "a.mp4"}, {"file": "b.mp4"}, {"file": "c.mp4"}]
    pick, state = Server.next_from_bag(entries, Server._empty_shuffle())
    assert pick["file"] == "c.mp4"

    # Act: d.mp4 arrived. c.mp4 already played, so it stays out until the reshuffle.
    grown = entries + [{"file": "d.mp4"}]
    rest = []
    for _ in range(3):
        pick, state = Server.next_from_bag(grown, state)
        rest.append(pick["file"])

    assert rest == ["b.mp4", "a.mp4", "d.mp4"]

    # Act: b.mp4 is gone. Only a and c are left, and the saved deck still names b.
    state = {"deck": ["a.mp4", "b.mp4", "c.mp4"], "last": "", "pool": ["a.mp4", "b.mp4", "c.mp4"]}
    left = [{"file": "a.mp4"}, {"file": "c.mp4"}]
    first, state = Server.next_from_bag(left, state)
    second, state = Server.next_from_bag(left, state)

    assert first["file"] == "c.mp4"
    assert second["file"] == "a.mp4"
    assert "b.mp4" not in state["deck"]
    assert "b.mp4" not in state["pool"]


def test_pick_local_clip_saves_the_bag_and_skips_a_repeat(monkeypatch):
    """The bag is clips_cache/shuffle.json. The next redeem does not repeat the file just played."""

    folder = Server.CLIPS_DIR
    folder.mkdir()
    rows = []
    for name in ("a.mp4", "b.mp4"):
        (folder / name).write_bytes(b"not really a video")
        rows.append({
            "file": name,
            "clip_id": name[:-4],
            "url": "https://clips.twitch.tv/" + name,
            "embed_url": "",
            "title": name,
            "broadcaster_name": "Durotan_Live",
            "creator": "Peonwork",
            "duration": 4,
            "view_count": 3,
            "source": "wow",
            "rank": 1,
            "thumbnail_url": "",
        })
    (folder / "index.json").write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setattr(Server.random, "shuffle", keep_order)

    # Act
    first = Server.pick_local_clip()
    second = Server.pick_local_clip()
    third = Server.pick_local_clip()

    # Assert
    assert first["file"] == "b.mp4"
    assert second["file"] == "a.mp4"
    assert third["file"] != second["file"]
    saved = json.loads((folder / "shuffle.json").read_text(encoding="utf-8"))
    assert saved["last"] == third["file"]
    assert isinstance(saved["deck"], list)


def test_clear_clip_cache_keeps_the_shuffle_bag():
    """Startup deletes old mp4s and leaves shuffle.json, so the round can continue."""

    folder = Server.CLIPS_DIR
    folder.mkdir()
    (folder / "old.mp4").write_bytes(b"old")
    (folder / "shuffle.json").write_text("{}\n", encoding="utf-8")
    (folder / ".gitkeep").write_text("", encoding="utf-8")

    # Act
    Server.clear_clip_cache()

    # Assert
    assert (folder / "shuffle.json").is_file()
    assert (folder / ".gitkeep").is_file()
    assert not (folder / "old.mp4").is_file()
