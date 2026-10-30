"""Example unit tests. Read tests/README.md."""

import hashlib
import hmac
import json
from datetime import datetime, timezone

import pytest

import gemini_usage
import Server

# Must match EVENTSUB_SECRET in tests/conftest.py.
TEST_SECRET = "unit-test-eventsub-secret"


def signed_headers(raw_body, message_id, message_type="notification"):
    """Headers Twitch would send for this exact body and secret."""

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    digest = hmac.new(
        TEST_SECRET.encode("utf-8"),
        message_id.encode("utf-8") + timestamp.encode("utf-8") + raw_body,
        hashlib.sha256,
    ).hexdigest()
    return {
        "Twitch-Eventsub-Message-Id": message_id,
        "Twitch-Eventsub-Message-Timestamp": timestamp,
        "Twitch-Eventsub-Message-Signature": "sha256=" + digest,
        "Twitch-Eventsub-Message-Type": message_type,
        "Content-Type": "application/json",
    }


@pytest.fixture(autouse=True)
def clean_server_state(monkeypatch, tmp_path):
    """Give every test an empty feed, a fresh credits file, and no remembered message ids."""

    Server.EVENT_ID = 0
    Server.EVENTS.clear()
    Server.TR_CACHE.clear()
    Server._last_voice_line = None
    with Server._seen_lock:
        Server._seen_ids.clear()
        Server._seen_set.clear()
    Server._counsel_last_ask.clear()
    monkeypatch.setattr(Server, "CREDITS_FILE", tmp_path / "stream_credits.json")
    monkeypatch.setattr(gemini_usage, "USAGE_FILE", tmp_path / "gemini_usage.json")


@pytest.fixture
def client():
    """A fake browser/Twitch that talks to the Flask app without opening a port."""

    Server.app.config["TESTING"] = True
    return Server.app.test_client()


def test_valid_signature_is_accepted(client):
    """A webhook signed with our secret is accepted."""

    # Arrange: a redemption Twitch might send, signed the same way Twitch signs.
    body = {
        "subscription": {
            "type": "channel.channel_points_custom_reward_redemption.add",
        },
        "event": {
            "id": "redeem-1",
            "user_name": "RemyFriend",
            "user_login": "remyfriend",
            "user_input": "",
            "reward": {"id": "reward-1", "title": "Not A Real Reward"},
        },
    }
    raw = json.dumps(body).encode("utf-8")
    headers = signed_headers(raw, message_id="msg-valid")

    # Act: post those exact bytes to the webhook.
    response = client.post("/webhook", data=raw, headers=headers)

    # Assert: Twitch got a success, so it will not retry or revoke us.
    assert response.status_code == 200


def test_invalid_signature_is_rejected(client):
    """A webhook with a forged signature is refused."""

    # Arrange: start from a real signature, then replace it with garbage.
    raw = b'{"event": {}}'
    headers = signed_headers(raw, message_id="msg-bad")
    headers["Twitch-Eventsub-Message-Signature"] = "sha256=" + ("ab" * 32)

    # Act
    response = client.post("/webhook", data=raw, headers=headers)

    # Assert: strangers cannot fire rewards, and nothing was published.
    assert response.status_code == 403
    assert len(Server.EVENTS) == 0


def test_tunnel_guard_blocks_forwarded_events(client):
    """A request that came through ngrok cannot read the local event feed."""

    # Arrange: ngrok adds this header when it forwards someone from the internet.
    headers = {"X-Forwarded-For": "203.0.113.5"}

    # Act
    response = client.get("/events", headers=headers)

    # Assert
    assert response.status_code == 403


def test_events_feed_contract(client):
    """Widgets can poll /events. Ids only go up, and last_id is sent even when nothing is new."""

    # Arrange: the feed starts empty.

    # Act
    empty = client.get("/events?since=-1")

    # Assert: since=-1 asks for the backlog. An empty feed still reports last_id.
    assert empty.status_code == 200
    payload = empty.get_json()
    assert payload["events"] == []
    assert payload["last_id"] == 0
    assert empty.headers["Access-Control-Allow-Origin"] == "*"
    assert empty.headers["Cache-Control"] == "no-store"

    # Arrange: two follows land in the feed.
    Server.publish("follow", user="First", login="first")
    Server.publish("follow", user="Second", login="second")

    # Act
    everything = client.get("/events?since=-1").get_json()
    only_second = client.get("/events?since=1").get_json()

    # Assert: ids are 1 then 2, and since=1 skips the first.
    assert [item["id"] for item in everything["events"]] == [1, 2]
    assert everything["last_id"] == 2
    assert everything["events"][0]["type"] == "follow"
    assert everything["events"][0]["user"] == "First"
    assert [item["id"] for item in only_second["events"]] == [2]
    assert only_second["last_id"] == 2


def test_credits_list_each_viewer_once():
    """The same viewer is thanked once, even if that credit happens twice."""

    # Arrange: clean_server_state points the credits file at a temp folder.

    # Act
    Server.add_credit("subs", user="RemyFriend", login="remyfriend")
    Server.add_credit("subs", user="RemyFriend", login="remyfriend")

    # Assert
    saved = json.loads(Server.CREDITS_FILE.read_text(encoding="utf-8"))
    assert [entry["user"] for entry in saved["subs"]] == ["RemyFriend"]


def test_translate_returns_text_and_detected_language(client, monkeypatch):
    """GET /translate returns the JSON the widget expects, without calling the internet."""

    # Arrange: pretend Google's free endpoint answered. No real HTTP leaves the test.
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            # Same shape as translate.googleapis.com: segments, then the detected language.
            return [[["Hi chat!", "hola chat"]], None, "es"]

    def fake_get(url, params=None, timeout=None, **kwargs):
        calls.append({"url": url, "params": params})
        return FakeResponse()

    monkeypatch.setattr(Server.requests, "get", fake_get)

    # Act
    response = client.get("/translate", query_string={"text": "hola chat", "target": "en"})

    # Assert
    assert response.status_code == 200
    assert response.get_json() == {
        "text": "Hi chat!",
        "source": "es",
        "target": "en",
        "detected": "es",
    }
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert len(calls) == 1
    assert "translate.googleapis.com" in calls[0]["url"]
    assert calls[0]["params"]["q"] == "hola chat"
    assert calls[0]["params"]["tl"] == "en"


def test_play_a_clip_publishes_clip_and_voice_line(monkeypatch, tmp_path):
    """Play a Clip asks Helix for a clip, picks a local voice line, and publishes both."""

    # Arrange: two fake recordings, and Helix replaced by a function that returns one clip.
    orc = tmp_path / "orc"
    orc.mkdir()
    (orc / "hello.mp3").write_bytes(b"not really audio")
    (orc / "charge.wav").write_bytes(b"not really audio")
    monkeypatch.setattr(Server, "VOICE_LINES_DIR", tmp_path)
    monkeypatch.setenv("BROADCASTER_USER_ID", "12345")

    seen = {}

    def fake_token():
        return "app-token"

    def fake_clips(token, broadcaster_id):
        seen["token"] = token
        seen["broadcaster_id"] = broadcaster_id
        return [{
            "id": "ClipId",
            "url": "https://clips.twitch.tv/ClipId",
            "embed_url": "https://clips.twitch.tv/embed?clip=ClipId",
            "title": "Big pull",
            "creator_name": "Someone",
            "duration": 12.5,
            "thumbnail_url": "https://example.test/thumb.jpg",
        }]

    monkeypatch.setattr(Server.clips, "get_app_token", fake_token)
    monkeypatch.setattr(Server.clips, "get_broadcaster_clips", fake_clips)

    # Act: call the reward function directly, so we don't wait on a background thread.
    Server.play_clip_for("RemyFriend", "remyfriend")

    # Assert
    assert len(Server.EVENTS) == 1
    event = Server.EVENTS[0]
    assert event["type"] == "clip"
    assert event["user"] == "RemyFriend"
    assert event["login"] == "remyfriend"
    assert event["clip_id"] == "ClipId"
    assert event["clip_url"] == "https://clips.twitch.tv/ClipId"
    assert event["embed_url"] == "https://clips.twitch.tv/embed?clip=ClipId"
    assert event["title"] == "Big pull"
    assert event["creator"] == "Someone"
    assert event["duration"] == 12.5
    assert event["thumbnail_url"] == "https://example.test/thumb.jpg"
    assert event["voice_line"] in {
        "/voice_lines/orc/hello.mp3",
        "/voice_lines/orc/charge.wav",
    }
    assert seen["token"] == "app-token"
    assert seen["broadcaster_id"] == "12345"


def test_widgets_are_local_files_inside_one_folder(client, monkeypatch, tmp_path):
    """A widget file is served from WIDGETS_DIR. The URL cannot leave that folder, and ngrok cannot read it."""

    # Arrange: one widget file, and a secret that sits next to the folder, not inside it.
    widgets = tmp_path / "widgets"
    (widgets / "orc").mkdir(parents=True)
    (widgets / "orc" / "index.html").write_text("<p>orc widget</p>", encoding="utf-8")
    secret = tmp_path / "secret.txt"
    secret.write_text("top-secret", encoding="utf-8")
    monkeypatch.setenv("WIDGETS_DIR", str(widgets))

    # Act
    served = client.get("/widgets/orc/index.html")

    # Assert
    assert served.status_code == 200
    assert b"orc widget" in served.data

    # Act: climb out of the widgets folder toward secret.txt.
    escaped = client.get("/widgets/../secret.txt")

    # Assert: the secret is not in the response.
    assert escaped.status_code == 404
    assert b"top-secret" not in escaped.data

    # Act: the same file, forwarded by ngrok.
    forwarded = client.get(
        "/widgets/orc/index.html",
        headers={"X-Forwarded-For": "203.0.113.5"},
    )

    # Assert
    assert forwarded.status_code == 403


def test_counsel_blocked_word_does_not_call_gemini(client, monkeypatch, tmp_path):
    """A banned word gets a canned saying. Gemini is never called, and the word is not echoed."""

    # Arrange: one banned word, and a Gemini stand-in that fails the test if it is used.
    words = tmp_path / "banned.txt"
    words.write_text("nope\n", encoding="utf-8")
    monkeypatch.setattr(Server, "BANNED_WORDS_FILE", words)
    Server._banned_cache["mtime"] = None
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    def fake_post(*args, **kwargs):
        raise AssertionError("Gemini should not be called for a blocked question")

    monkeypatch.setattr(Server.requests, "post", fake_post)

    # Act
    response = client.get("/counsel", query_string={"q": "is this nope okay", "user": "Remy"})

    # Assert
    assert response.status_code == 200
    body = response.get_json()
    assert body["source"] == "canned"
    assert body["answer"] in Server.MONK_SAYINGS
    assert "nope" not in body["answer"].lower()
    assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert response.headers["Cache-Control"] == "no-store"


def test_counsel_cooldown_returns_canned(client, monkeypatch):
    """The same viewer gets one Gemini answer, then a canned saying until the cooldown ends."""

    # Arrange: Gemini returns one fixed sentence. The key here is fake.
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("COUNSEL_USER_COOLDOWN", "60")
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "candidates": [{
                    "content": {"parts": [{"text": "Sip your tea, then decide."}]},
                }],
            }

    def fake_post(url, headers=None, timeout=None, json=None, **kwargs):
        calls.append(url)
        return FakeResponse()

    monkeypatch.setattr(Server.requests, "post", fake_post)

    # Act
    first = client.get("/counsel", query_string={"q": "tank or healer", "user": "Remy"})
    second = client.get("/counsel", query_string={"q": "what about dps", "user": "Remy"})

    # Assert
    assert first.status_code == 200
    assert first.get_json() == {
        "answer": "Sip your tea, then decide.",
        "source": "gemini",
    }
    assert second.status_code == 200
    assert second.get_json()["source"] == "canned"
    assert second.get_json()["answer"] in Server.MONK_SAYINGS
    assert len(calls) == 1


def test_counsel_is_blocked_through_the_tunnel(client, monkeypatch):
    """ngrok cannot spend the Gemini quota. A forwarded /counsel is refused."""

    # Arrange: a key is set, and any real call would fail this test.
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    def fake_post(*args, **kwargs):
        raise AssertionError("Gemini should not be called through the tunnel")

    monkeypatch.setattr(Server.requests, "post", fake_post)

    # Act
    response = client.get(
        "/counsel",
        query_string={"q": "tank or healer", "user": "Remy"},
        headers={"X-Forwarded-For": "203.0.113.5"},
    )

    # Assert
    assert response.status_code == 403
