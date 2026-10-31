# Tests, the short version

These tests check Production Center without Twitch, OBS, or the internet. The files in `tests/` are examples you can copy when you want to check a new behavior.

## What a unit test is

A unit test is a small program that checks one behavior.

It sets something up, does one action, and checks the result. If the check is wrong, the test fails and tells you what it expected. You can run the same checks every time you change the server, instead of clicking through OBS and Twitch by hand.

A test does not start `Server.py`. It imports the file and calls the pieces directly, or talks to Flask through a fake client that never opens port 5000.

## What mocking is

A mock is a stand-in. You replace a slow or dangerous function with a tiny one you control.

We mock OBS, Twitch, and text-to-speech because:

- OBS is not running on every machine, and a test should not move sources on a live stream.
- Twitch calls need real tokens and would create real subscriptions.
- edge-tts and Google Translate need the network, and they can change or rate-limit.

The test still runs the Production Center code. Only the outside world is fake. `monkeypatch` puts the fake in place for one test and removes it when the test ends.

Look at `test_translate_returns_text_and_detected_language` in `tests/test_examples.py`. `fake_get` records the URL and returns a made-up Google response. This line installs it:

```python
monkeypatch.setattr(Server.requests, "get", fake_get)
```

After that, any `requests.get` inside `Server.py` hits `fake_get` instead of the internet. The asserts then check both the JSON and that we called Google's host once with the text `hola chat`.

`test_play_a_clip_publishes_clip_and_voice_line` does the same kind of swap for `clips.get_app_token` and `clips.get_top_wow_clips`, and points `VOICE_LINES_DIR` at a temp folder. `test_play_a_clip_with_no_wow_clips_publishes_empty_fields` uses an empty list from that stand-in and checks that the clip fields stay blank.

`test_welcome_message_creates_subscriptions` swaps `requests.post` the same way, so a welcome message can create subscriptions without calling Helix. It also swaps `websocket.create_connection` so the test fails if a real socket opens.

## How to run

From the project folder:

```bash
pip install -r requirements-dev.txt
pytest -v
```

`requirements-dev.txt` installs the app packages and pytest. `-v` prints one line per test instead of a dot. If the `pytest` command is not found, use `python -m pytest -v` instead.

Run one test by name:

```bash
pytest -v tests/test_examples.py::test_welcome_message_creates_subscriptions
```

## How to read the output

A passing run looks like this:

```text
tests/test_examples.py::test_welcome_message_creates_subscriptions PASSED
tests/test_examples.py::test_notification_publishes_to_events PASSED
...
======= 14 passed in 0.20s =======
```

`PASSED` means every `assert` in that test was true.

A failure names the test, then shows the line that broke and an assertion error. Read the bottom of the traceback first. That is the `assert` that failed. Above it is the path of calls that got there. Pytest often prints `where` the two sides differed:

```text
E       AssertionError: assert 403 == 200
E        +  where 403 = <WrapperTestResponse ...>.status_code
```

The test wanted status 200 and the app returned 403. Fix the app or fix the test, then run pytest again. You do not need to restart anything.

`FAILED` stops that one test. The others still run. The last line is the count: `6 passed, 1 failed`.

## The files pytest uses for you

`tests/conftest.py` runs before the tests. You never call it. It adds the project folder to the import path and sets fake OBS and Twitch ids so importing `Server.py` does not need your real `.env`. Those values are not your tokens.

`clean_server_state` in `tests/test_examples.py` runs before every test (`autouse=True`). It empties the event feed, forgets message ids, and points the credits file at a temp folder so tests do not write `stream_credits.json` in the project.

`client` is Flask's test client. `client.post` and `client.get` call the routes in-process. `127.0.0.1` is the remote address, so the localhost check treats them as local unless you add a forwarding header.

## One test, line by line

This is `test_welcome_message_creates_subscriptions`. It proves a welcome message creates the EventSub subscriptions and sends the session id from that message.

```python
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
```

`def test_welcome_message_creates_subscriptions(monkeypatch):`
Pytest runs any function whose name starts with `test_`. `monkeypatch` is a fixture pytest gives you. You do not call it yourself. It lets this test replace functions, then puts the originals back when the test ends.

`"""A session_welcome creates each subscription with that session id."""`
The docstring is for humans. It says what a pass is supposed to prove. The `# Proves:` comment under it says the same thing in the test body.

`client = Server.EventSubClient()`
This builds the WebSocket helper without starting its background thread and without opening a socket. The test calls `handle_message` directly, the same function the real socket calls when a message arrives.

`posts = []` and `fake_post`
`fake_post` has the same arguments `requests.post` uses. It saves each call in `posts` and returns a tiny object with status 202, which is what Twitch sends when a WebSocket subscription is accepted. Nothing leaves the computer.

`fail_connect`
If the welcome path tried to open a second socket, this stand-in would crash the test. That is how we know the subscription uses HTTP, not another WebSocket.

`monkeypatch.setattr(...)`
These four lines install the fakes and the fake Twitch ids for this test only. `TWITCH_OAUTH_TOKEN` here is the word `user-token-for-test`. It is not a real token.

The rest of the test (the Act and the Assert) builds a welcome message with `session_id` `session-abc`, calls `client.handle_message(welcome)`, and checks six things:

- the call returned `"welcome"`
- the keepalive number from the message was stored (`12`)
- Helix was called once for each event type
- every call used `transport.method` `websocket` and `session_id` `session-abc`
- the follow subscription is version `2` and sets `moderator_user_id` to the broadcaster id

Read `test_notification_publishes_to_events` next. It feeds a follow notification and checks that the same handler runs and that `/events` got one follow. `test_duplicate_message_id_is_ignored` sends that follow twice with the same id and expects a single event. `test_session_reconnect_switches_url` uses `FakeSocket` instead of a real WebSocket and checks that the client connects to the new URL, reads the welcome, and only then closes the old socket.

## How to write a new test

1. Copy a test in `tests/test_examples.py` and rename it. Names read like a sentence: `test_duplicate_message_id_is_ignored`.
2. Put a one-line comment that says what a pass proves.
3. Change the Arrange so the scene matches the idea. Use `monkeypatch` when the idea says to mock.
4. Keep a single Act.
5. Assert the expected status, JSON, or function call. One behavior per test is enough.
6. Run `pytest -v` and read the bottom line.

Do not point a test at real Twitch or a live OBS. If a test needs a file, use pytest's `tmp_path` (a temp folder that goes away after the test) the way the credits and clip tests do.
