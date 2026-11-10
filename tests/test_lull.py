"""Lull posts one short grounded answer. Whisper, Gemini, and Helix are fakes."""

import json
import time

import pytest

import gemini_usage
import lull

BOT = "bot-user-99"
TOKEN = "bot-oauth-for-test"
KEY = "gemini-key-for-test"


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def gemini_body(text, thought=""):
    parts = []
    if thought:
        parts.append({"thought": True, "text": thought})
    parts.append({"text": text})
    return {"candidates": [{"content": {"parts": parts}}]}


class Router:
    def __init__(self, answer="Paris is the capital of France."):
        self.calls = []
        self.gemini_status = 200
        self.gemini = gemini_body(answer)
        self.helix_status = 200
        self.helix = {"data": [{"is_sent": True, "message_id": "m1"}]}

    def __call__(self, url, **kwargs):
        self.calls.append({
            "url": url,
            "headers": kwargs.get("headers") or {},
            "json": kwargs.get("json") or {},
        })
        if "generateContent" in url:
            return FakeResponse(self.gemini_status, self.gemini)
        return FakeResponse(self.helix_status, self.helix)


def gemini_calls(router):
    return [call for call in router.calls if "generateContent" in call["url"]]


def helix_calls(router):
    return [call for call in router.calls if call["url"] == lull.HELIX_CHAT]


@pytest.fixture
def usage_file(monkeypatch, tmp_path):
    monkeypatch.setattr(gemini_usage, "USAGE_FILE", tmp_path / "gemini_usage.json")


def arm(monkeypatch, router):
    monkeypatch.setenv("GEMINI_API_KEY", KEY)
    monkeypatch.setenv("TWITCH_BOT_OAUTH_TOKEN", TOKEN)
    monkeypatch.setenv("TWITCH_BOT_USER_ID", BOT)
    monkeypatch.setenv("TWITCH_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("BROADCASTER_USER_ID", "12345")
    monkeypatch.setenv("LULL_COOLDOWN", "15")
    monkeypatch.delenv("LULL_MODEL", raising=False)
    monkeypatch.delenv("LULL_HOTKEY", raising=False)
    monkeypatch.setattr(lull.requests, "post", router)
    lull.bind_censor(lambda text: text)


def wait_until(predicate, seconds=2):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class FakeCapture:
    def __init__(self, device):
        self.device = device
        self.reads = 0
        self.closed = False

    def read(self, stop):
        self.reads += 1
        if self.reads == 1:
            return [0.0] * 160
        stop.wait(0.2)
        return None

    def close(self):
        self.closed = True


class Script:
    def __init__(self, text):
        self.text = text
        self.seen = 0

    def transcribe(self, samples):
        self.seen += 1
        return self.text


def test_grounding_tool_and_default_model(monkeypatch, usage_file):
    router = Router()
    arm(monkeypatch, router)

    assert lull.answer_question("what is the capital of France") is True

    assert len(gemini_calls(router)) == 1
    call = gemini_calls(router)[0]
    assert call["json"]["tools"] == [{"google_search": {}}]
    assert "gemini-3.6-flash" in call["url"]
    assert KEY not in call["url"]
    assert call["headers"]["x-goog-api-key"] == KEY
    assert call["json"]["contents"][0]["parts"][0]["text"] == "what is the capital of France"
    assert lull.hotkey_name() == "f3"


def test_long_answer_trims_under_the_chat_limit():
    sentence = ("The short fact is this. " * 40).strip()
    trimmed = lull.trim_answer(sentence)
    assert len(trimmed) <= 300
    assert trimmed.endswith(".")

    spaced = "word " * 120
    assert len(lull.trim_answer(spaced)) <= 300

    wall = "x" * 800
    assert len(lull.trim_answer(wall)) == 500

    marked = "**Paris** is the capital."
    assert lull.trim_answer(marked) == "Paris is the capital."


def test_censor_runs_before_the_message_is_posted(monkeypatch, usage_file):
    import Server

    router = Router("this is nope today")
    arm(monkeypatch, router)
    monkeypatch.setattr(Server, "banned_words", lambda: ("nope",))
    lull.bind_censor(Server.censor_viewer_text)

    assert lull.answer_question("say the word") is True

    message = helix_calls(router)[0]["json"]["message"]
    assert message == "this is **** today"
    assert "nope" not in message


def test_helix_body_and_headers(monkeypatch, usage_file):
    router = Router("Paris is the capital of France.")
    arm(monkeypatch, router)

    assert lull.answer_question("capital?") is True

    call = helix_calls(router)[0]
    assert call["headers"]["Client-Id"] == "test-client-id"
    assert call["headers"]["Authorization"] == f"Bearer {TOKEN}"
    assert call["json"] == {
        "broadcaster_id": "12345",
        "sender_id": BOT,
        "message": "Paris is the capital of France.",
    }


@pytest.mark.parametrize("status", [401, 403])
def test_refused_chat_logs_status_without_the_token(monkeypatch, usage_file, capsys, status):
    router = Router()
    router.helix_status = status
    router.helix = {"message": TOKEN, "key": KEY}
    arm(monkeypatch, router)

    assert lull.answer_question("where is the french government based") is False

    output = capsys.readouterr().out
    assert f"Twitch chat refused: {status}" in output
    assert "Paris is the capital of France." in output
    assert TOKEN not in output
    assert KEY not in output
    assert "where is the french government based" not in output


def test_is_sent_false_logs_the_drop_reason(monkeypatch, usage_file, capsys):
    router = Router()
    router.helix = {"data": [{"is_sent": False, "drop_reason": "msg_rejected", "message": TOKEN}]}
    arm(monkeypatch, router)

    assert lull.answer_question("capital?") is False

    output = capsys.readouterr().out
    assert "msg_rejected" in output
    assert TOKEN not in output
    assert KEY not in output


def test_cooldown_allows_one_hold(monkeypatch, usage_file):
    router = Router()
    arm(monkeypatch, router)

    assert lull.answer_question("first question") is True
    assert lull.answer_question("second question") is False

    assert len(gemini_calls(router)) == 1
    assert len(helix_calls(router)) == 1


def test_empty_speech_does_not_call_gemini_or_helix(monkeypatch, usage_file):
    router = Router()
    arm(monkeypatch, router)

    assert lull.answer_question("   ") is False
    assert router.calls == []


def test_missing_bot_token_does_not_call_gemini(monkeypatch, usage_file, capsys):
    router = Router()
    arm(monkeypatch, router)
    monkeypatch.delenv("TWITCH_BOT_OAUTH_TOKEN", raising=False)

    assert lull.answer_question("what time is it") is False

    output = capsys.readouterr().out
    assert "Chat skipped" in output
    assert router.calls == []
    assert KEY not in output
    assert "what time is it" not in output


def test_hold_release_transcribes_once_and_posts_once(monkeypatch, usage_file):
    router = Router("It is noon.")
    arm(monkeypatch, router)
    script = Script("what time is it")
    talk = lull.PushToTalk(
        transcriber_factory=lambda name: script,
        capture_factory=FakeCapture,
    )

    assert talk.key_down() is True
    assert talk.key_down() is False
    assert wait_until(lambda: talk._audio)
    assert talk.key_up() is True
    assert talk.key_up() is False
    assert wait_until(lambda: talk.snapshot()["state"] == "idle")

    assert script.seen == 1
    assert len(gemini_calls(router)) == 1
    asked = gemini_calls(router)[0]["json"]["contents"][0]["parts"][0]["text"]
    assert asked == "what time is it"
    assert helix_calls(router)[0]["json"]["message"] == "It is noon."
    assert talk.snapshot()["recording"] is False


def test_thought_text_is_not_the_answer(monkeypatch, usage_file):
    router = Router()
    router.gemini = gemini_body("The public answer.", thought="hidden reasoning " + TOKEN)
    arm(monkeypatch, router)

    assert lull.answer_question("question") is True
    assert helix_calls(router)[0]["json"]["message"] == "The public answer."


def test_hotkey_bind_does_not_swallow_the_key_or_import_benito(monkeypatch):
    pressed = {}

    class Keyboard:
        def on_press_key(self, name, callback, suppress=True):
            pressed["down"] = (name, suppress)

        def on_release_key(self, name, callback, suppress=True):
            pressed["up"] = (name, suppress)

    monkeypatch.delenv("LULL_HOTKEY", raising=False)
    assert lull.start_hotkey(Keyboard()) is True
    assert pressed == {"down": ("f3", False), "up": ("f3", False)}
    source = open(lull.__file__, encoding="utf-8").read()
    imports = [
        line.strip()
        for line in source.splitlines()
        if line.startswith("import ") or line.startswith("from ")
    ]
    assert not any("Benito" in line or "pyautogui" in line for line in imports)
