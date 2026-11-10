"""Shoutout a Channel. Helix and the bot chat post are mocked."""

import pytest

import Server
import lull

TOKEN = "broadcaster-token-for-test"


class FakeResponse:
    def __init__(self, status, payload=None, body=""):
        self.status_code = status
        self._payload = payload
        self.text = body

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


@pytest.mark.parametrize(
    ("raw", "login"),
    [
        ("  Cool_Channel1  ", "cool_channel1"),
        ("@Cool_Channel1", "cool_channel1"),
        ("https://www.twitch.tv/Cool_Channel1", "cool_channel1"),
        ("http://twitch.tv/Cool_Channel1/", "cool_channel1"),
        ("HTTPS://m.twitch.tv/Cool_Channel1?ref=1", "cool_channel1"),
        ("twitch.tv/Cool_Channel1#live", "cool_channel1"),
    ],
)
def test_channel_name_is_cleaned(raw, login):
    assert Server.clean_channel_login(raw) == login


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "ab", "a" * 26, "has space", "bad-name", "nope!", "https://example.com/cool"],
)
def test_channel_name_must_be_a_login(raw):
    assert Server.clean_channel_login(raw) == ""


class Helix:
    def __init__(self, user=None, shout_status=204, shout_body=None):
        self.calls = []
        self.user = user
        self.shout_status = shout_status
        self.shout_body = shout_body if shout_body is not None else {}
        self.chats = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append({"method": "GET", "url": url, "headers": headers or {}})
        data = [] if self.user is None else [self.user]
        return FakeResponse(200, {"data": data})

    def post(self, url, headers=None, timeout=None, json=None):
        self.calls.append({
            "method": "POST",
            "url": url,
            "headers": headers or {},
            "json": json,
        })
        return FakeResponse(self.shout_status, self.shout_body, body=TOKEN)

    def chat(self, message):
        self.chats.append(message)
        return True


@pytest.fixture
def ready(monkeypatch):
    box = {}

    def install(helix):
        monkeypatch.setattr(Server, "TWITCH_CLIENT_ID", "test-client-id")
        monkeypatch.setattr(Server, "TWITCH_OAUTH_TOKEN", TOKEN)
        monkeypatch.setattr(Server, "BROADCASTER_USER_ID", "12345")
        monkeypatch.setattr(Server.requests, "get", helix.get)
        monkeypatch.setattr(Server.requests, "post", helix.post)
        monkeypatch.setattr(lull, "post_chat", helix.chat)
        box["helix"] = helix
        return helix

    return install


def test_missing_channel_posts_a_short_note(ready):
    helix = ready(Helix(user=None))

    assert Server.shoutout_channel("@nobodyhere", "Viewer") is False

    assert [call["method"] for call in helix.calls] == ["GET"]
    assert helix.calls[0]["url"] == "https://api.twitch.tv/helix/users?login=nobodyhere"
    assert helix.chats == ["Couldn't find twitch.tv/nobodyhere."]


def test_shoutout_request_uses_the_broadcaster_token(ready):
    helix = ready(Helix(user={
        "id": "999",
        "login": "cool_channel1",
        "display_name": "Cool_Channel1",
    }))

    assert Server.shoutout_channel("https://twitch.tv/Cool_Channel1", "RemyFriend") is True

    post = helix.calls[1]
    assert post["method"] == "POST"
    assert post["url"] == (
        "https://api.twitch.tv/helix/chat/shoutouts"
        "?from_broadcaster_id=12345&to_broadcaster_id=999&moderator_id=12345"
    )
    assert post["headers"]["Client-ID"] == "test-client-id"
    assert post["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert post["json"] is None
    assert helix.chats == [
        "Go check out Cool_Channel1 at twitch.tv/cool_channel1! (shoutout from RemyFriend)"
    ]


@pytest.mark.parametrize("status", [429, 400])
def test_rate_limit_or_rejection_still_posts_the_chat_line(ready, capsys, status):
    helix = ready(Helix(
        user={"id": "999", "login": "cool_channel1", "display_name": "Cool_Channel1"},
        shout_status=status,
        shout_body={"message": "The broadcaster is not live"},
    ))

    assert Server.shoutout_channel("cool_channel1", "RemyFriend") is False

    output = capsys.readouterr().out
    assert str(status) in output
    assert "The broadcaster is not live" in output
    assert TOKEN not in output
    assert helix.chats == [
        "Go check out Cool_Channel1 at twitch.tv/cool_channel1! (shoutout from RemyFriend)"
    ]


def test_401_names_the_scope_and_hides_the_token(ready, capsys):
    helix = ready(Helix(
        user={"id": "999", "login": "cool_channel1", "display_name": "Cool_Channel1"},
        shout_status=401,
        shout_body={"message": TOKEN},
    ))

    assert Server.shoutout_channel("cool_channel1", "RemyFriend") is False

    output = capsys.readouterr().out
    assert "401" in output
    assert "moderator:manage:shoutouts" in output
    assert TOKEN not in output
    assert helix.chats == []


def test_names_in_the_chat_line_are_censored(monkeypatch, ready):
    monkeypatch.setattr(Server, "banned_words", lambda: ("nope",))
    helix = ready(Helix(user={
        "id": "999",
        "login": "cool_channel1",
        "display_name": "nope",
    }))

    assert Server.shoutout_channel("cool_channel1", "nope") is True

    assert helix.chats == [
        "Go check out **** at twitch.tv/cool_channel1! (shoutout from ****)"
    ]
    assert "nope" not in helix.chats[0]


def test_reward_title_starts_one_thread(monkeypatch):
    made = []

    class FakeThread:
        def __init__(self, target=None, args=(), daemon=None):
            self.target = target
            self.args = args
            self.daemon = daemon
            self.started = False
            made.append(self)

        def start(self):
            self.started = True

    monkeypatch.setattr(Server, "Thread", FakeThread)
    event = {
        "reward": {"title": "  SHOUTOUT a channel "},
        "user_name": "RemyFriend",
        "user_input": "@cool_channel1",
    }
    Server.route_channel_point_reward(event)
    Server.route_channel_point_reward({"reward": {"title": "Shoutout"}, "user_input": "x"})

    assert len(made) == 1
    assert made[0].started is True
    assert made[0].daemon is True
    assert made[0].target == Server.shoutout_channel
    assert made[0].args == ("@cool_channel1", "RemyFriend")
