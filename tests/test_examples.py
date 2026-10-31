"""Example unit tests. Read tests/README.md."""

import json

import pytest

import gemini_usage
import Server


def ws_message(message_type, payload, message_id):
    """One EventSub WebSocket message, in the shape Twitch sends."""

    return {
        "metadata": {
            "message_id": message_id,
            "message_type": message_type,
            "message_timestamp": "2026-01-01T00:00:00.000Z",
        },
        "payload": payload,
    }


class FakeResponse:
    """Stands in for the object requests.post returns."""

    def __init__(self, status_code=202, text=""):
        self.status_code = status_code
        self.text = text


class FakeSocket:
    """A pretend WebSocket. recv hands back canned text, then says the line is idle."""

    def __init__(self, name, incoming, order):
        self.name = name
        self.incoming = list(incoming)
        self.order = order
        self.closed = False

    def recv(self):
        if not self.incoming:
            raise Server.websocket.WebSocketTimeoutException("idle")
        self.order.append(f"recv {self.name}")
        return self.incoming.pop(0)

    def settimeout(self, seconds):
        # The real socket uses this to cap how long recv waits.
        return None

    def close(self):
        self.order.append(f"close {self.name}")
        self.closed = True


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
    # A real clips_cache on this PC must not change Play a Clip tests.
    monkeypatch.setattr(Server, "CLIPS_DIR", tmp_path / "clips_cache")


@pytest.fixture
def client():
    """A fake browser/Twitch that talks to the Flask app without opening a port."""

    Server.app.config["TESTING"] = True
    return Server.app.test_client()


def test_welcome_message_creates_subscriptions(monkeypatch):
    """A session_welcome creates each subscription with that session id."""

    # Proves: the welcome message is what tells us to call Helix, and the
    # session id from that message is the one we send.

    # Arrange: Helix is a fake. A real socket must not open.
    client = Server.EventSubClient()
    posts = []

    def fake_post(url, headers=None, json=None, timeout=None):
        posts.append({"url": url, "headers": headers, "json": json})
        return FakeResponse(status_code=202)

    def fail_connect(*args, **kwargs):
        raise AssertionError("welcome subscribes over HTTP and does not open another socket")

    monkeypatch.setattr(Server.requests, "post", fake_post)
    monkeypatch.setattr(Server.websocket, "create_connection", fail_connect)
    monkeypatch.setattr(Server, "TWITCH_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(Server, "TWITCH_OAUTH_TOKEN", "user-token-for-test")
    monkeypatch.setattr(Server, "BROADCASTER_USER_ID", "12345")

    welcome = ws_message(
        "session_welcome",
        {
            "session": {
                "id": "session-abc",
                "status": "connected",
                "keepalive_timeout_seconds": 12,
            },
        },
        message_id="welcome-1",
    )

    # Act
    result = client.handle_message(welcome)

    # Assert: one Helix call per event type, all tied to this session.
    assert result == "welcome"
    assert client.keepalive_timeout == 12
    assert len(posts) == 6
    types = [item["json"]["type"] for item in posts]
    assert types == [
        "channel.channel_points_custom_reward_redemption.add",
        "channel.follow",
        "channel.subscribe",
        "channel.subscription.gift",
        "channel.subscription.message",
        "channel.cheer",
    ]
    for item in posts:
        assert item["url"] == Server.EVENTSUB_URL
        assert item["headers"]["Client-ID"] == "test-client-id"
        assert item["headers"]["Authorization"] == "Bearer user-token-for-test"
        assert item["json"]["transport"] == {
            "method": "websocket",
            "session_id": "session-abc",
        }
    follow = posts[1]["json"]
    assert follow["version"] == "2"
    assert follow["condition"] == {
        "broadcaster_user_id": "12345",
        "moderator_user_id": "12345",
    }


def test_notification_publishes_to_events(monkeypatch):
    """A notification uses the same handler and shows up on /events."""

    # Proves: a follow on the socket becomes one follow event in the feed.

    # Arrange: remember the handler call, then run the real one.
    client = Server.EventSubClient()
    seen = []
    real_handler = Server.handle_notification

    def spy(sub_type, event):
        seen.append((sub_type, event))
        return real_handler(sub_type, event)

    def fail_post(*args, **kwargs):
        raise AssertionError("a notification must not create subscriptions")

    def fail_connect(*args, **kwargs):
        raise AssertionError("a notification must not open a socket")

    monkeypatch.setattr(Server, "handle_notification", spy)
    monkeypatch.setattr(Server.requests, "post", fail_post)
    monkeypatch.setattr(Server.websocket, "create_connection", fail_connect)

    notice = ws_message(
        "notification",
        {
            "subscription": {"type": "channel.follow", "status": "enabled"},
            "event": {"user_name": "RemyFriend", "user_login": "remyfriend"},
        },
        message_id="notice-1",
    )

    # Act
    result = client.handle_message(notice)

    # Assert
    assert result == "notification"
    assert seen == [(
        "channel.follow",
        {"user_name": "RemyFriend", "user_login": "remyfriend"},
    )]
    assert len(Server.EVENTS) == 1
    assert Server.EVENTS[0]["type"] == "follow"
    assert Server.EVENTS[0]["user"] == "RemyFriend"
    assert Server.EVENTS[0]["login"] == "remyfriend"


def test_duplicate_message_id_is_ignored(monkeypatch):
    """The same message id does not publish twice."""

    # Proves: a second copy of a message is dropped before the handler runs.

    # Arrange: the same follow, same id, twice.
    client = Server.EventSubClient()
    calls = []
    real_handler = Server.handle_notification

    def spy(sub_type, event):
        calls.append(sub_type)
        return real_handler(sub_type, event)

    monkeypatch.setattr(Server, "handle_notification", spy)
    notice = ws_message(
        "notification",
        {
            "subscription": {"type": "channel.follow"},
            "event": {"user_name": "RemyFriend", "user_login": "remyfriend"},
        },
        message_id="notice-same",
    )

    # Act
    first = client.handle_message(notice)
    second = client.handle_message(notice)

    # Assert
    assert first == "notification"
    assert second == "duplicate"
    assert calls == ["channel.follow"]
    assert len(Server.EVENTS) == 1


def test_session_reconnect_switches_url(monkeypatch):
    """session_reconnect connects to the new URL and closes the old socket after welcome."""

    # Proves: we follow Twitch's reconnect URL, and we do not subscribe again.

    # Arrange: the old socket is open. The new one has a welcome waiting.
    order = []
    old = FakeSocket("old", [], order)
    welcome = json.dumps(ws_message(
        "session_welcome",
        {
            "session": {
                "id": "session-abc",
                "keepalive_timeout_seconds": 10,
            },
        },
        message_id="welcome-2",
    ))
    new = FakeSocket("new", [welcome], order)
    reconnect_url = "wss://eventsub.wss.twitch.tv/reconnect?id=1"

    def fake_connect(url, timeout=None):
        order.append(("connect", url))
        return new

    def fail_subscribe(session_id):
        raise AssertionError("a reconnect must keep the old subscriptions")

    monkeypatch.setattr(Server.websocket, "create_connection", fake_connect)
    monkeypatch.setattr(Server, "subscribe_to_events", fail_subscribe)

    client = Server.EventSubClient()
    client._ws = old
    client.reconnect_welcome_wait = 1
    reconnect = ws_message(
        "session_reconnect",
        {"session": {"reconnect_url": reconnect_url}},
        message_id="reconnect-1",
    )

    # Act
    result = client.handle_message(reconnect)

    # Assert: connect, read the welcome, then close the old socket.
    assert result == "reconnect"
    assert order == [
        ("connect", reconnect_url),
        "recv new",
        "close old",
    ]
    assert client.url == reconnect_url
    assert client._ws is new
    assert old.closed is True
    assert new.closed is False


def test_tunnel_guard_blocks_forwarded_events(client):
    """A forwarded request cannot read the local event feed."""

    # Arrange: a proxy adds this header. This server only answers this PC.
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
    """Play a Clip asks for a top WoW clip, picks a local voice line, and publishes both."""

    # Proves: the clip on the orc event is one that get_top_wow_clips returned,
    # and a voice line from the orc folder goes out with it. No Twitch call.

    # Arrange: two fake recordings, and the WoW list replaced by one clip.
    orc = tmp_path / "orc"
    orc.mkdir()
    (orc / "hello.mp3").write_bytes(b"not really audio")
    (orc / "charge.wav").write_bytes(b"not really audio")
    monkeypatch.setattr(Server, "VOICE_LINES_DIR", tmp_path)
    # This reward no longer reads the channel id. Remove it so a leftover
    # requirement would fail the test instead of quietly using the fake id.
    monkeypatch.delenv("BROADCASTER_USER_ID", raising=False)

    seen = {}

    def fake_token():
        return "app-token"

    def fake_wow_clips(token):
        seen["token"] = token
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
    monkeypatch.setattr(Server.clips, "get_top_wow_clips", fake_wow_clips)

    # Act: call the reward function directly, so we don't wait on a background thread.
    Server.play_clip_for("RemyFriend", "remyfriend")

    # Assert: the published clip is the one from the fake WoW list.
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


def test_play_a_clip_with_no_wow_clips_publishes_empty_fields(monkeypatch, tmp_path):
    """An empty WoW clip list still publishes a clip event with blank clip fields."""

    # Proves: zero clips from get_top_wow_clips does not crash. The orc event
    # still goes out, and the clip fields are empty instead of made-up data.

    # Arrange: no voice files, and the WoW lookup returns an empty list.
    monkeypatch.setattr(Server, "VOICE_LINES_DIR", tmp_path)
    monkeypatch.delenv("BROADCASTER_USER_ID", raising=False)

    seen = {}

    def fake_token():
        return "app-token"

    def fake_wow_clips(token):
        seen["token"] = token
        return []

    monkeypatch.setattr(Server.clips, "get_app_token", fake_token)
    monkeypatch.setattr(Server.clips, "get_top_wow_clips", fake_wow_clips)

    # Act
    Server.play_clip_for("RemyFriend", "remyfriend", "Play a Clip")

    # Assert: one clip event, and every clip field is blank.
    assert seen["token"] == "app-token"
    assert len(Server.EVENTS) == 1
    event = Server.EVENTS[0]
    assert event["type"] == "clip"
    assert event["user"] == "RemyFriend"
    assert event["login"] == "remyfriend"
    assert event["clip_id"] == ""
    assert event["clip_url"] == ""
    assert event["embed_url"] == ""
    assert event["title"] == ""
    assert event["creator"] == ""
    assert event["duration"] == 0
    assert event["thumbnail_url"] == ""
    assert event["voice_line"] == ""
    assert event["reward"] == "Play a Clip"


def test_widgets_are_local_files_inside_one_folder(client, monkeypatch, tmp_path):
    """A widget file is served from WIDGETS_DIR. The URL cannot leave that folder, and a forwarded request cannot read it."""

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

    # Act: the same file, with a forwarding header.
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
    """A forwarded /counsel is refused, so it cannot spend the Gemini quota."""

    # Arrange: a key is set, and any real call would fail this test.
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    def fake_post(*args, **kwargs):
        raise AssertionError("Gemini should not be called for a forwarded request")

    monkeypatch.setattr(Server.requests, "post", fake_post)

    # Act
    response = client.get(
        "/counsel",
        query_string={"q": "tank or healer", "user": "Remy"},
        headers={"X-Forwarded-For": "203.0.113.5"},
    )

    # Assert
    assert response.status_code == 403
