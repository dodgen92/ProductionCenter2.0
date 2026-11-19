"""StreamElements Astro -> WoW chat feed. The socket is fake. No token leaves the feed or the log."""

import json

import pytest

import Server
import streamelements_chat
from websocket import ABNF

# Long on purpose. Short strings are not treated as secrets.
TOKEN = "super-secret-se-token-xyz"
OTHER = "second-secret-se-token-xyz"
RECONNECT = "reconnect-token-xyz-987"


class FakeFrame:
    def __init__(self, opcode, data):
        self.opcode = opcode
        self.data = data


class FakeSocket:
    """Stands in for websocket-client. Records what we send and the PONGs."""

    def __init__(self, frames):
        self.frames = list(frames)
        self.sent = []
        self.pongs = []
        self.closed = False

    def recv_frame(self):
        if not self.frames:
            raise streamelements_chat.websocket.WebSocketConnectionClosedException("closed")
        return self.frames.pop(0)

    def send(self, data):
        self.sent.append(data)

    def pong(self, data):
        self.pongs.append(data)

    def settimeout(self, seconds):
        return None

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def clean_feed():
    streamelements_chat.reset_feed()
    yield
    streamelements_chat.reset_feed()


@pytest.fixture
def client():
    Server.app.config["TESTING"] = True
    return Server.app.test_client()


def envelope(provider, text, **extra):
    """One channel.chat message, in the shape Astro sends."""

    author = {
        "id": extra.get("user_id", "user-9"),
        "login": extra.get("login", "viewer"),
        "name": extra.get("name", "Viewer"),
        "roles": extra.get("roles", ["moderator"]),
    }
    data = {
        "v": 1,
        "event": "message",
        "provider": provider,
        "channel": {"id": "chan", "provider_id": "1", "login": "tyler"},
        "sent_at": "2026-11-03T11:37:58Z",
        "id": extra.get("message_id", "msg-1"),
        "author": author,
        "text": text,
        "kind": extra.get("kind", "text"),
    }
    if "fragments" in extra:
        data["fragments"] = extra["fragments"]
        if text is None:
            data.pop("text")
    return {
        "id": "01ULID",
        "ts": "2026-11-03T11:37:58Z",
        "type": "message",
        "topic": "channel.chat",
        "room": "chan",
        "data": data,
    }


def client_with(token=TOKEN, room="room-1", token_type="jwt"):
    return streamelements_chat.AstroClient(
        [{"token": token, "room": room}],
        token_type=token_type,
        enabled=True,
    )


def test_youtube_message_is_relayed():
    """A YouTube channel.chat message becomes one feed line with the role and kind."""

    # Proves: the widget feed gets YouTube text, and the provider is normalized.
    astro = client_with()
    status = astro.handle_message(
        None,
        envelope("YouTube", "hello from youtube", kind="action", roles=["subscriber"]),
    )

    assert status == "relay"
    feed = streamelements_chat.feed_since(0)
    assert feed["last_seq"] == 1
    line = feed["messages"][0]
    assert line["provider"] == "youtube"
    assert line["text"] == "hello from youtube"
    assert line["kind"] == "action"
    assert line["roles"] == ["subscriber"]
    assert line["message_id"] == "msg-1"
    assert line["seq"] == 1


def test_kick_message_is_relayed():
    """A Kick message is relayed the same way, with the Kick provider."""

    astro = client_with()
    status = astro.handle_message(None, envelope("kick", "hello from kick", name="Kicker"))

    assert status == "relay"
    line = streamelements_chat.feed_since(0)["messages"][0]
    assert line["provider"] == "kick"
    assert line["name"] == "Kicker"
    assert line["text"] == "hello from kick"


def test_twitch_and_other_providers_are_ignored():
    """Twitch is already on IRC. x and anything else are not drawn."""

    # Proves: ignored providers never reach the word filter or the feed.
    def boom(text):
        raise AssertionError(text)

    for provider in ("twitch", "x", "facebook"):
        assert streamelements_chat.normalize_chat(
            {"event": "message", "provider": provider, "text": "hi", "id": "m"},
            boom,
        ) is None

    astro = client_with()
    assert astro.handle_message(None, envelope("twitch", "should not show")) == "ignored"
    assert streamelements_chat.feed_since(0)["messages"] == []


def test_moderation_events_are_relayed_for_youtube_and_kick():
    """Deletes, timeouts, and a cleared chat are forwarded. Twitch clears stay on IRC."""

    astro = client_with()
    astro.handle_message(None, envelope("youtube", "keep me", message_id="keep"))
    astro.handle_message(None, envelope("kick", "drop me", message_id="drop", user_id="spammer"))
    deleted = astro.handle_message(None, {
        "type": "message",
        "topic": "channel.chat",
        "data": {
            "v": 1,
            "event": "message_deleted",
            "provider": "youtube",
            "message_id": "keep",
        },
    })
    cleared_user = astro.handle_message(None, {
        "type": "message",
        "topic": "channel.chat",
        "data": {
            "v": 1,
            "event": "user_cleared",
            "provider": "kick",
            "user": {"id": "spammer", "login": "spammer", "name": "Spammer"},
            "duration_seconds": 600,
        },
    })
    astro.handle_message(None, envelope("kick", "still here", message_id="later"))
    cleared = astro.handle_message(None, {
        "type": "message",
        "topic": "channel.chat",
        "data": {"v": 1, "event": "chat_cleared", "provider": "kick"},
    })

    assert deleted == "relay"
    assert cleared_user == "relay"
    assert cleared == "relay"
    events = [(item["event"], item["provider"]) for item in streamelements_chat.feed_since(0)["messages"]]
    # The Kick lines were removed from the backlog. The YouTube delete stays so the widget can drop it.
    assert ("message", "kick") not in events
    assert ("message_deleted", "youtube") in events
    assert ("user_cleared", "kick") in events
    assert ("chat_cleared", "kick") in events
    assert events[-1] == ("chat_cleared", "kick")


def test_deleted_id_drops_a_message_that_arrives_late():
    """A delete can show up before its message. That message is not relayed."""

    astro = client_with()
    astro.handle_message(None, {
        "type": "message",
        "topic": "channel.chat",
        "data": {
            "event": "message_deleted",
            "provider": "youtube",
            "message_id": "late-1",
        },
    })
    status = astro.handle_message(None, envelope("youtube", "too late", message_id="late-1"))

    assert status == "ignored"
    texts = [item.get("text") for item in streamelements_chat.feed_since(0)["messages"]]
    assert "too late" not in texts


def test_duplicate_message_is_relayed_once():
    astro = client_with()
    astro.handle_message(None, envelope("youtube", "once", message_id="same"))
    second = astro.handle_message(None, envelope("youtube", "once", message_id="same"))

    assert second == "ignored"
    messages = streamelements_chat.feed_since(0)["messages"]
    assert len(messages) == 1
    assert messages[0]["text"] == "once"


def test_fragments_are_used_when_text_is_missing():
    """A fragment we do not know is still drawn as its text."""

    event = streamelements_chat.normalize_chat(
        {
            "event": "message",
            "provider": "kick",
            "id": "m",
            "author": {"name": "A"},
            "fragments": [
                {"type": "mystery", "text": "hello "},
                {"type": "emote", "text": "Kappa"},
            ],
        },
        lambda text: text,
    )

    assert event["text"] == "hello Kappa"


def test_unknown_event_and_topic_are_ignored():
    astro = client_with()
    assert streamelements_chat.normalize_chat(
        {"event": "superchat", "provider": "youtube", "text": "hi"},
        lambda text: text,
    ) is None
    assert astro.handle_message(None, {
        "type": "message",
        "topic": "channel.activities",
        "data": {"provider": "youtube", "event": "message", "text": "nope"},
    }) == "ignored"
    assert streamelements_chat.feed_since(0)["messages"] == []


def test_viewer_text_is_censored():
    """YouTube and Kick text uses the same banned-word filter as other viewer text."""

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(Server, "banned_words", lambda: ("spoiler",))
    try:
        astro = client_with()
        astro.handle_message(None, envelope("youtube", "a spoiler here"))
        line = streamelements_chat.feed_since(0)["messages"][0]
        assert line["text"] == "a ******* here"
        assert line["name"] == "Viewer"
    finally:
        monkeypatch.undo()


def test_ping_is_answered_with_pong():
    """Astro's keepalive is a websocket PING. We answer with the same payload."""

    astro = client_with()
    sock = FakeSocket([])
    status = astro.handle_frame(sock, FakeFrame(ABNF.OPCODE_PING, b"ping-body"))

    assert status == "pong"
    assert sock.pongs == [b"ping-body"]


def test_read_loop_pongs_subscribes_relays_and_reconnects(monkeypatch, capsys):
    """One fake socket: PONG, subscribe, relay, then the reconnect token.

    The next connection uses that token and does not subscribe again.
    The account token is not in the log or in the reconnect URL.
    """

    welcome = {"type": "welcome", "data": {"client_id": "client-1", "message": "hi"}}
    reconnect = {"type": "reconnect", "data": {"reconnect_token": RECONNECT, "message": "shutting down"}}
    frames = [
        FakeFrame(ABNF.OPCODE_PING, b"ping-body"),
        FakeFrame(ABNF.OPCODE_TEXT, json.dumps(welcome).encode()),
        FakeFrame(ABNF.OPCODE_TEXT, json.dumps(envelope("youtube", "hello from youtube")).encode()),
        FakeFrame(ABNF.OPCODE_TEXT, json.dumps(reconnect).encode()),
    ]
    sock = FakeSocket(frames)
    urls = []

    def connect(url, timeout=None):
        urls.append(url)
        return sock

    monkeypatch.setattr(streamelements_chat.websocket, "create_connection", connect)
    astro = client_with()
    astro._connect_and_read()

    assert sock.pongs == [b"ping-body"]
    assert urls == [streamelements_chat.ASTRO_URL]
    sent = json.loads(sock.sent[0])
    assert sent["type"] == "subscribe"
    assert sent["data"]["topic"] == "channel.chat"
    assert sent["data"]["token"] == TOKEN
    assert sent["data"]["token_type"] == "jwt"
    assert sent["data"]["room"] == "room-1"
    assert streamelements_chat.feed_since(0)["messages"][0]["text"] == "hello from youtube"
    assert astro.reconnect_token == RECONNECT

    sock2 = FakeSocket([FakeFrame(ABNF.OPCODE_TEXT, json.dumps(welcome).encode())])

    def connect_again(url, timeout=None):
        urls.append(url)
        return sock2

    monkeypatch.setattr(streamelements_chat.websocket, "create_connection", connect_again)
    astro._connect_and_read()

    assert "reconnect_token=" + RECONNECT in urls[-1]
    assert TOKEN not in urls[-1]
    assert sock2.sent == []
    logged = capsys.readouterr().out
    assert TOKEN not in logged
    assert RECONNECT not in logged


def test_backoff_grows_and_stops_at_thirty_seconds():
    astro = streamelements_chat.AstroClient([])
    astro.backoff = 1
    assert astro.take_delay() == 1
    assert astro.backoff == 2
    astro.backoff = 16
    assert astro.take_delay() == 16
    assert astro.backoff == 30
    assert astro.take_delay() == 30
    assert astro.backoff == 30


def test_missing_token_does_not_connect(monkeypatch, capsys):
    """No token: the server starts, and the websocket is never opened."""

    monkeypatch.delenv("STREAMELEMENTS_TOKEN", raising=False)
    monkeypatch.delenv("STREAMELEMENTS_ENABLED", raising=False)
    monkeypatch.delenv("STREAMELEMENTS_CHANNEL_ID", raising=False)

    def fail_connect(*args, **kwargs):
        raise AssertionError("missing token must not open a socket")

    monkeypatch.setattr(streamelements_chat.websocket, "create_connection", fail_connect)
    astro = streamelements_chat.AstroClient.from_env()

    assert astro.start() is False
    assert astro._thread is None
    assert "No STREAMELEMENTS_TOKEN" in capsys.readouterr().out


def test_switch_off_does_not_connect_or_log_the_token(monkeypatch, capsys):
    monkeypatch.setenv("STREAMELEMENTS_TOKEN", TOKEN)
    monkeypatch.setenv("STREAMELEMENTS_ENABLED", "off")
    monkeypatch.setenv("STREAMELEMENTS_CHANNEL_ID", "room-1")

    def fail_connect(*args, **kwargs):
        raise AssertionError("the off switch must not open a socket")

    monkeypatch.setattr(streamelements_chat.websocket, "create_connection", fail_connect)
    astro = streamelements_chat.AstroClient.from_env()

    assert astro.enabled is False
    assert astro.start() is False
    logged = capsys.readouterr().out
    assert "STREAMELEMENTS_ENABLED is off" in logged
    assert TOKEN not in logged


def test_token_never_appears_in_logs_or_the_feed(capsys):
    """A chat line and an error that echo the token are redacted before they are stored or printed."""

    astro = client_with()
    astro.handle_message(None, envelope("youtube", "look " + TOKEN + " oops", name=TOKEN))
    astro.handle_message(None, {
        "type": "response",
        "error": "err_unauthorized",
        "data": {"message": "rejected " + TOKEN},
    })

    body = json.dumps(streamelements_chat.feed_since(0))
    logged = capsys.readouterr().out
    assert TOKEN not in body
    assert TOKEN not in logged
    assert "[redacted]" in body
    assert "[redacted]" in logged
    line = streamelements_chat.feed_since(0)["messages"][0]
    assert line["text"] == "look [redacted] oops"
    assert line["name"] == "[redacted]"


def test_connection_error_redacts_the_token(monkeypatch, capsys):
    def fail_connect(url, timeout=None):
        raise OSError("could not connect with " + TOKEN + " url " + url)

    monkeypatch.setattr(streamelements_chat.websocket, "create_connection", fail_connect)
    astro = client_with()
    astro.reconnect_token = RECONNECT
    astro._connect_and_read()

    logged = capsys.readouterr().out
    assert TOKEN not in logged
    assert RECONNECT not in logged
    assert "[redacted]" in logged


def test_comma_separated_tokens_and_token_type(monkeypatch, capsys):
    """Two tokens subscribe separately. One channel id is reused. apikey is passed through."""

    slept = []
    monkeypatch.setattr(streamelements_chat.time, "sleep", lambda seconds: slept.append(seconds))
    accounts = streamelements_chat.parse_accounts(TOKEN + ", " + OTHER, "room-a, room-b")
    astro = streamelements_chat.AstroClient(accounts, token_type="apikey", enabled=True)
    sock = FakeSocket([])
    astro.handle_message(sock, {"type": "welcome", "data": {"client_id": "c"}})

    assert slept == [0.11]
    payloads = [json.loads(raw) for raw in sock.sent]
    assert payloads[0]["data"]["token"] == TOKEN
    assert payloads[0]["data"]["room"] == "room-a"
    assert payloads[0]["data"]["token_type"] == "apikey"
    assert payloads[1]["data"]["token"] == OTHER
    assert payloads[1]["data"]["room"] == "room-b"
    assert payloads[0]["nonce"] != payloads[1]["nonce"]

    reused = streamelements_chat.parse_accounts(TOKEN + "," + OTHER, "only-room")
    assert reused[0]["room"] == "only-room"
    assert reused[1]["room"] == "only-room"
    bare = client_with(room="").subscribe_payload({"token": TOKEN, "room": ""})
    assert "room" not in bare["data"]

    monkeypatch.setenv("STREAMELEMENTS_TOKEN", TOKEN)
    monkeypatch.delenv("STREAMELEMENTS_TOKEN_TYPE", raising=False)
    assert streamelements_chat.AstroClient.from_env().token_type == "jwt"
    monkeypatch.setenv("STREAMELEMENTS_TOKEN_TYPE", "bearer")
    assert streamelements_chat.AstroClient.from_env().token_type == "jwt"
    assert TOKEN not in capsys.readouterr().out


def test_feed_endpoint_returns_new_lines_and_hides_the_token(client):
    """GET /wow-chat/feed is the widget's poll. since= skips lines it already has."""

    astro = client_with()
    astro.handle_message(None, envelope("youtube", "hello from youtube " + TOKEN, message_id="m-feed"))
    first = client.get("/wow-chat/feed?since=0")

    assert first.status_code == 200
    assert first.content_type.startswith("application/json")
    body = first.get_data(as_text=True)
    assert TOKEN not in body
    payload = first.get_json()
    assert payload["messages"][0]["provider"] == "youtube"
    assert payload["messages"][0]["text"] == "hello from youtube [redacted]"
    assert "<" not in payload["messages"][0]["text"]

    second = client.get("/wow-chat/feed?since=%s" % payload["last_seq"])
    assert second.get_json()["messages"] == []
    assert second.get_json()["last_seq"] == payload["last_seq"]


def test_feed_keeps_html_as_text(client):
    """The feed is JSON text. The widget escapes it. The route does not serve the line as HTML."""

    raw = '<img src=x onerror=alert(1)>'
    astro = client_with()
    astro.handle_message(None, envelope("kick", raw, message_id="html-1"))
    response = client.get("/wow-chat/feed?since=0")

    assert response.content_type.startswith("application/json")
    assert response.get_json()["messages"][0]["text"] == raw


def test_feed_is_local_only(client):
    response = client.get("/wow-chat/feed?since=0", headers={"X-Forwarded-For": "8.8.8.8"})

    assert response.status_code == 403
    assert TOKEN not in response.get_data(as_text=True)
