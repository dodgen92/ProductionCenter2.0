"""Benito's chat gate, Ask Benito, the slide-up widget, and translate output.

Twitch, the clock, chat sending, and key presses are stand-ins.
Nothing in this file touches WoW or the network.
"""

from pathlib import Path

import pytest

import gemini_usage
import benito_control
import Server


ROOT = Path(__file__).resolve().parents[1]
WIDGET = ROOT / "widgets" / "benito-answer"


class ImmediateThread:
    """Run the worker now, so a test does not wait on a real thread."""

    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self.target = target
        self.args = args or ()

    def start(self):
        if self.target:
            self.target(*self.args)


@pytest.fixture(autouse=True)
def clean_benito(monkeypatch, tmp_path):
    """Empty feed, a fresh gate, and no Gemini key left over from a real .env."""

    Server.EVENT_ID = 0
    Server.EVENTS.clear()
    Server.TR_CACHE.clear()
    Server._banned_cache["mtime"] = None
    monkeypatch.setattr(gemini_usage, "USAGE_FILE", tmp_path / "gemini_usage.json")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("WIDGETS_DIR", raising=False)
    monkeypatch.setenv("BENITO_CONTROL_BITS", "107")
    monkeypatch.setenv("BENITO_CONTROL_SECONDS", "600")
    monkeypatch.setattr(Server, "benito_gate", benito_control.BenitoControl())
    monkeypatch.setattr(Server, "BROADCASTER_USER_ID", "12345")

    def fail_key(keybind):
        raise AssertionError(f"key pressed without a mock: {keybind}")

    monkeypatch.setattr(Server, "press_benito_keybind", fail_key)


@pytest.fixture
def client():
    Server.app.config["TESTING"] = True
    return Server.app.test_client()


@pytest.fixture
def chats(monkeypatch):
    sent = []
    monkeypatch.setattr(Server, "send_chat", lambda message: sent.append(message) or True)
    return sent


@pytest.fixture
def keys(monkeypatch):
    pressed = []
    monkeypatch.setattr(Server, "press_benito_keybind", lambda keybind: pressed.append(keybind))
    return pressed


def cheer(bits, user_id, name, login, anonymous=False):
    Server.handle_notification("channel.cheer", {
        "is_anonymous": anonymous,
        "user_id": None if anonymous else user_id,
        "user_name": None if anonymous else name,
        "user_login": None if anonymous else login,
        "bits": bits,
    })


def chat(user_id, text, name="River", login="river"):
    Server.handle_notification("channel.chat.message", {
        "broadcaster_user_id": "12345",
        "chatter_user_id": user_id,
        "chatter_user_login": login,
        "chatter_user_name": name,
        "message": {"text": text},
    })


def control_events():
    return [event for event in Server.EVENTS if event["type"] == "benito_control"]


def test_exact_107_grants_control(chats):
    """107 bits gives that user exclusive control and tells chat."""

    cheer(107, "55", "River", "river")

    assert Server.benito_gate.holder["user_id"] == "55"
    assert chats == [
        "@river, Benito is yours for 10 minutes! Earth Mother guide your paws.",
    ]
    started = control_events()
    assert len(started) == 1
    assert started[0]["reason"] == "start"
    assert started[0]["mode"] == "exclusive"
    assert started[0]["user"] == "River"
    assert started[0]["login"] == "river"
    assert started[0]["user_id"] == "55"
    assert started[0]["seconds"] == 600
    assert any(event["type"] == "bits" and event["amount"] == 107 for event in Server.EVENTS)


def test_other_bit_amounts_are_ignored(chats):
    """100 and 108 do not grant control. An anonymous 107 does not either."""

    cheer(100, "1", "Ann", "ann")
    cheer(108, "2", "Bob", "bob")
    cheer(107, "3", "Anon", "anon", anonymous=True)

    assert chats == []
    assert Server.benito_gate.holder is None
    assert control_events() == []
    bits = [event for event in Server.EVENTS if event["type"] == "bits"]
    assert [event["amount"] for event in bits] == [100, 108, 107]


def test_queue_handoff_after_expiry(monkeypatch, chats, keys):
    """The next cheerer gets their 10 minutes when the current one ends."""

    clock = {"t": 1000.0}
    gate = benito_control.BenitoControl(clock=lambda: clock["t"])
    monkeypatch.setattr(Server, "benito_gate", gate)

    cheer(107, "55", "River", "river")
    cheer(107, "66", "Moss", "moss")

    assert gate.holder["user_id"] == "55"
    assert [person["user_id"] for person in gate.queue] == ["66"]
    assert "@moss, Benito is with someone else. The Earth Mother has your place in line." in chats

    clock["t"] = 1600.0
    Server.poll_benito_control()

    assert gate.holder["user_id"] == "66"
    assert list(gate.queue) == []
    assert "@river, your time is up. Earth Mother calls him back." in chats
    assert "@moss, Benito is yours for 10 minutes! Earth Mother guide your paws." in chats

    chat("55", "!rejuv", name="River", login="river")
    chat("66", "!rejuv", name="Moss", login="moss")
    assert keys == ["1"]
    commands = [event for event in Server.EVENTS if event["type"] == "benito_command"]
    assert len(commands) == 1
    assert commands[0]["user"] == "Moss"
    assert commands[0]["keybind"] == "1"
    assert commands[0]["target"] == "Remy"


def test_all_chat_by_default_and_after_the_queue_empties(monkeypatch, chats, keys):
    """With nobody holding him, any viewer can command. That returns when the line is empty."""

    assert Server.benito_gate.holder is None
    chat("77", "!wrath", name="Dee", login="dee")
    assert keys == ["5"]
    first = [event for event in Server.EVENTS if event["type"] == "benito_command"][0]
    assert first["command"] == "!wrath"
    assert first["target"] == "Remy's target"
    assert first["user"] == "Dee"

    clock = {"t": 0.0}
    gate = benito_control.BenitoControl(clock=lambda: clock["t"])
    monkeypatch.setattr(Server, "benito_gate", gate)
    cheer(107, "55", "River", "river")
    clock["t"] = 600.0
    Server.poll_benito_control()

    assert gate.holder is None
    assert "Benito is listening to all of chat again." in chats
    opened = control_events()[-1]
    assert opened["reason"] == "open"
    assert opened["mode"] == "all"

    chat("88", "!bear", name="Pip", login="pip")
    assert keys[-1] == "Shift+5"
    bear = [event for event in Server.EVENTS if event["type"] == "benito_command"][-1]
    assert bear["command"] == "!bear"
    assert bear["target"] == "Benito"
    assert bear["user"] == "Pip"


def test_non_controller_commands_are_ignored(chats, keys):
    """While someone holds Benito, other viewers' spells do nothing."""

    cheer(107, "55", "River", "river")
    chat("77", "!moonfire", name="Dee", login="dee")

    assert keys == []
    assert [event for event in Server.EVENTS if event["type"] == "benito_command"] == []

    chat("55", "!Moonfire", name="River", login="river")
    assert keys == ["4"]
    command = [event for event in Server.EVENTS if event["type"] == "benito_command"][0]
    assert command["command"] == "!moonfire"
    assert command["keybind"] == "4"
    assert command["target"] == "Remy's target"
    assert command["user"] == "River"


def test_benitokick_only_works_for_the_broadcaster_id(chats, keys):
    """A mod who copies the broadcaster's name cannot end the turn. The id can."""

    cheer(107, "55", "River", "river")
    cheer(107, "66", "Moss", "moss")

    chat("999", "!benitokick", name="Tyler", login="tyler")

    assert Server.benito_gate.holder["user_id"] == "55"
    assert "your time is up" not in " ".join(chats)
    assert keys == []

    chat("12345", "!BenitoKick", name="NotTyler", login="someoneelse")

    assert Server.benito_gate.holder["user_id"] == "66"
    assert "@river, your time is up. Earth Mother calls him back." in chats
    assert "@moss, Benito is yours for 10 minutes! Earth Mother guide your paws." in chats
    reasons = [event["reason"] for event in control_events()]
    assert "kick" in reasons
    assert keys == []


@pytest.mark.parametrize("command,keybind,target", benito_control.BENITO_KEYBINDS)
def test_command_parsing_includes_targets(command, keybind, target):
    """Every bind matches case-insensitively, with the target from the table."""

    parsed = benito_control.parse_command(command.upper())
    assert parsed == {"command": command, "keybind": keybind, "target": target}


def test_near_miss_commands_are_not_commands():
    """Extra words, and party targets on the wrong spell, are ignored."""

    assert benito_control.parse_command("!rejuv please") is None
    assert benito_control.parse_command("!regrowth party2") is None
    assert benito_control.parse_command("!fireball") is None
    assert benito_control.parse_command("!benitokick") is None


def test_translate_output_is_censored(client, monkeypatch, tmp_path):
    """A banned word that appears only in the translation is starred before the widget sees it."""

    words = tmp_path / "banned.txt"
    words.write_text("nope\n", encoding="utf-8")
    monkeypatch.setattr(Server, "BANNED_WORDS_FILE", words)
    Server._banned_cache["mtime"] = None

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [[["this is nope", "hola"]], None, "es"]

    monkeypatch.setattr(Server.requests, "get", lambda *args, **kwargs: FakeResponse())

    response = client.get("/translate", query_string={"text": "hola", "target": "en"})

    assert response.status_code == 200
    assert response.get_json()["text"] == "this is ****"
    assert "nope" not in response.get_json()["text"]


def test_ask_benito_event_shape(monkeypatch):
    """A redemption publishes user, question, answer, and the deep voice settings."""

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(Server, "Thread", ImmediateThread)

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "candidates": [{
                    "content": {"parts": [{"text": "The Earth Mother would have you rest."}]},
                }],
            }

    calls = []

    def fake_post(url, headers=None, timeout=None, json=None, **kwargs):
        calls.append({"url": url, "json": json})
        return FakeResponse()

    monkeypatch.setattr(Server.requests, "post", fake_post)

    Server.handle_notification(
        "channel.channel_points_custom_reward_redemption.add",
        {
            "id": "red-1",
            "user_id": "55",
            "user_login": "river",
            "user_name": "River",
            "user_input": "Should I heal?",
            "reward": {"id": "reward-1", "title": "Ask Benito"},
        },
    )

    answers = [event for event in Server.EVENTS if event["type"] == "benito_answer"]
    assert len(answers) == 1
    answer = answers[0]
    assert answer["user"] == "River"
    assert answer["login"] == "river"
    assert answer["question"] == "Should I heal?"
    assert answer["answer"] == "The Earth Mother would have you rest."
    assert answer["voice"] == "en-US-ChristopherNeural"
    assert answer["rate"] == "-10%"
    assert answer["pitch"] == "-60Hz"
    assert answer["voice"] in Server.TTS_VOICES
    assert "en-US-GuyNeural" in Server.TTS_VOICES
    assert len(calls) == 1
    assert "generateContent" in calls[0]["url"]
    instruction = calls[0]["json"]["system_instruction"]["parts"][0]["text"]
    assert "Tauren druid of Mulgore" in instruction


def test_ask_benito_censors_question_and_answer(monkeypatch, tmp_path):
    """Banned words are starred on the way in and on the way out."""

    words = tmp_path / "banned.txt"
    words.write_text("nope\n", encoding="utf-8")
    monkeypatch.setattr(Server, "BANNED_WORDS_FILE", words)
    Server._banned_cache["mtime"] = None
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "candidates": [{
                    "content": {"parts": [{"text": "nope indeed"}]},
                }],
            }

    seen = {}

    def fake_post(url, headers=None, timeout=None, json=None, **kwargs):
        seen["question"] = json["contents"][0]["parts"][0]["text"]
        return FakeResponse()

    monkeypatch.setattr(Server.requests, "post", fake_post)
    Server.publish_benito_answer("River", "river", "is nope ok")

    event = [item for item in Server.EVENTS if item["type"] == "benito_answer"][0]
    assert event["question"] == "is **** ok"
    assert event["answer"] == "**** indeed"
    assert seen["question"] == "is **** ok"
    assert "nope" not in event["question"]
    assert "nope" not in event["answer"]


def test_ask_benito_without_a_key_uses_a_fallback(monkeypatch):
    """No Gemini key still publishes a druid line, and does not call the network."""

    monkeypatch.setattr(Server.random, "choice", lambda seq: seq[0])

    def fail_post(*args, **kwargs):
        raise AssertionError("Gemini should not be called without a key")

    monkeypatch.setattr(Server.requests, "post", fail_post)
    Server.publish_benito_answer("River", "river", "Who are you?")

    event = [item for item in Server.EVENTS if item["type"] == "benito_answer"][0]
    assert event["answer"] == Server.BENITO_FALLBACKS[0]
    assert event["voice"] == Server.BENITO_VOICE


def test_send_chat_posts_to_helix(monkeypatch):
    """Chat lines go out as the broadcaster user token. The scope is user:write:chat."""

    posts = []

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"data": [{"is_sent": True, "drop_reason": None}]}

    def fake_post(url, headers=None, json=None, timeout=None, **kwargs):
        posts.append({"url": url, "headers": headers, "json": json})
        return FakeResponse()

    monkeypatch.setattr(Server.requests, "post", fake_post)
    monkeypatch.setattr(Server, "TWITCH_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(Server, "TWITCH_OAUTH_TOKEN", "user-token-for-test")
    monkeypatch.setattr(Server, "BROADCASTER_USER_ID", "12345")

    assert Server.send_chat("Hello grove") is True
    assert posts[0]["url"] == "https://api.twitch.tv/helix/chat/messages"
    assert posts[0]["headers"]["Authorization"] == "Bearer user-token-for-test"
    assert posts[0]["headers"]["Client-ID"] == "test-client-id"
    assert posts[0]["json"] == {
        "broadcaster_id": "12345",
        "sender_id": "12345",
        "message": "Hello grove",
    }


def test_prompt_is_the_druid_persona():
    """Benito.py and Ask Benito share the owner's identity text. Hunter gear is gone."""

    source = (ROOT / "Benito" / "Benito.py").read_text(encoding="utf-8")
    assert "Tauren druid of Mulgore" in source
    assert "antlered staff" in source
    assert "quiver" not in source.lower()
    assert "hunter" not in source.lower()
    assert "def send_keybind" in source

    def between(text, start, end):
        return text.split(start, 1)[1].split(end, 1)[0].strip()

    file_persona = between(source, "IDENTITY AND HISTORY:\n", "\nOUTPUT FORMAT:")
    ask_persona = between(Server.BENITO_ASK_PROMPT, "IDENTITY AND HISTORY:\n", "\nANSWER:")
    assert file_persona == ask_persona
    assert "never refer to keybinds" in ask_persona


def test_answer_widget_slides_up_and_speaks(client):
    """The widget page slides up on benito_answer and plays /tts with the event voice."""

    html = (WIDGET / "index.html").read_text(encoding="utf-8")
    js = (WIDGET / "benito.js").read_text(encoding="utf-8")
    css = (WIDGET / "style.css").read_text(encoding="utf-8")
    assert "benito.js" in html
    assert 'event.type === "benito_answer"' in js or 'event.type !== "benito_answer"' in js
    assert "/tts" in js
    assert "event.voice" in js
    assert "event.rate" in js
    assert "event.pitch" in js
    assert "translateY" in css
    assert "slideUp" in css
    pictures = list(WIDGET.rglob("*.png")) + list(WIDGET.rglob("*.webp")) + list(WIDGET.rglob("*.jpg"))
    assert pictures == []

    response = client.get("/widgets/benito-answer/index.html")
    assert response.status_code == 200
    assert b"Benito" in response.data
    script = client.get("/widgets/benito-answer/benito.js")
    assert script.status_code == 200
    assert b"benito_answer" in script.data
