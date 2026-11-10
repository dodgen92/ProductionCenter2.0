"""Change Stream Title. Helix is mocked. No token leaves the test."""

import pytest

import Server

TOKEN = "broadcaster-token-for-test"


class FakeResponse:
    def __init__(self, status, body=""):
        self.status_code = status
        self.text = body

    def json(self):
        return {}


class FakeThread:
    def __init__(self, target=None, args=(), daemon=None):
        self.target = target
        self.args = args
        self.daemon = daemon
        self.started = False

    def start(self):
        self.started = True


@pytest.fixture
def helix(monkeypatch):
    calls = []

    def fake_patch(url, headers=None, json=None, timeout=None):
        calls.append({
            "url": url,
            "headers": headers or {},
            "json": json or {},
            "timeout": timeout,
        })
        return FakeResponse(204)

    monkeypatch.setattr(Server, "TWITCH_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(Server, "TWITCH_OAUTH_TOKEN", TOKEN)
    monkeypatch.setattr(Server, "BROADCASTER_USER_ID", "12345")
    monkeypatch.setattr(Server.requests, "patch", fake_patch)
    return calls


def redeem(title, text="Raid night"):
    return {
        "reward": {"title": title},
        "user_name": "Viewer",
        "user_input": text,
    }


def test_title_match_starts_one_thread(monkeypatch):
    made = []

    def factory(*args, **kwargs):
        thread = FakeThread(*args, **kwargs)
        made.append(thread)
        return thread

    monkeypatch.setattr(Server, "Thread", factory)

    Server.route_channel_point_reward(redeem("Change Stream Title", "Hello chat"))
    Server.route_channel_point_reward(redeem("  change STREAM title  ", "Hello chat"))
    Server.route_channel_point_reward(redeem("Change Stream", "Hello chat"))

    assert len(made) == 2
    for thread in made:
        assert thread.started is True
        assert thread.daemon is True
        assert thread.target == Server.set_stream_title
        assert thread.args == ("Hello chat",)


def test_censor_is_applied_before_the_patch(monkeypatch, helix):
    monkeypatch.setattr(Server, "banned_words", lambda: ("nope",))

    assert Server.set_stream_title("hello nope tonight") is True

    assert helix[0]["json"] == {"title": "hello **** tonight"}
    assert "nope" not in helix[0]["json"]["title"]


def test_title_is_capped_at_140_characters(helix):
    assert Server.set_stream_title("x" * 200) is True

    title = helix[0]["json"]["title"]
    assert title == "x" * 140
    assert len(title) == 140


@pytest.mark.parametrize("text", ["", "   ", "\n\t", None])
def test_empty_title_is_ignored(helix, text):
    assert Server.set_stream_title(text) is False
    assert helix == []


def test_helix_url_headers_and_body(helix):
    assert Server.set_stream_title("  Raid night  ") is True

    call = helix[0]
    assert call["url"] == "https://api.twitch.tv/helix/channels?broadcaster_id=12345"
    assert call["headers"]["Client-ID"] == "test-client-id"
    assert call["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert call["headers"]["Content-Type"] == "application/json"
    assert call["json"] == {"title": "Raid night"}


@pytest.mark.parametrize("status", [401, 403])
def test_refused_title_tells_tyler_the_token_needs_the_scope(monkeypatch, capsys, status):
    def fake_patch(url, headers=None, json=None, timeout=None):
        return FakeResponse(status, body=TOKEN)

    monkeypatch.setattr(Server, "TWITCH_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(Server, "TWITCH_OAUTH_TOKEN", TOKEN)
    monkeypatch.setattr(Server, "BROADCASTER_USER_ID", "12345")
    monkeypatch.setattr(Server.requests, "patch", fake_patch)

    assert Server.set_stream_title("Raid night") is False

    output = capsys.readouterr().out
    assert str(status) in output
    assert "channel:manage:broadcast" in output
    assert TOKEN not in output
