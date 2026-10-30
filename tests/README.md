# Tests, the short version

These tests check Production Center without Twitch, OBS, ngrok, or the internet. The files in `tests/` are examples. `tests.txt` in the project folder is a list of tests for you to write.

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

`test_play_a_clip_publishes_clip_and_voice_line` does the same kind of swap for `clips.get_app_token` and `clips.get_broadcaster_clips`, and points `VOICE_LINES_DIR` at a temp folder.

## How to run

From the project folder:

```bash
pip install -r requirements-dev.txt
pytest -v
```

`requirements-dev.txt` installs the app packages and pytest. `-v` prints one line per test instead of a dot. If the `pytest` command is not found, use `python -m pytest -v` instead.

Run one test by name:

```bash
pytest -v tests/test_examples.py::test_valid_signature_is_accepted
```

## How to read the output

A passing run looks like this:

```text
tests/test_examples.py::test_valid_signature_is_accepted PASSED
tests/test_examples.py::test_invalid_signature_is_rejected PASSED
...
======= 8 passed in 0.20s =======
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

`tests/conftest.py` runs before the tests. You never call it. It adds the project folder to the import path and sets a fake `EVENTSUB_SECRET` so importing `Server.py` does not need your real `.env`. The secret in that file is not a Twitch secret. It only has to match `TEST_SECRET` in the test file.

`clean_server_state` in `tests/test_examples.py` runs before every test (`autouse=True`). It empties the event feed, forgets message ids, and points the credits file at a temp folder so tests do not write `stream_credits.json` in the project.

`client` is Flask's test client. `client.post` and `client.get` call the routes in-process. `127.0.0.1` is the remote address, so the tunnel guard treats them as local unless you add a forwarding header.

## One test, line by line

This is `test_valid_signature_is_accepted`. It proves a webhook signed with our secret is accepted.

```python
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
```

`def test_valid_signature_is_accepted(client):`
Pytest runs any function whose name starts with `test_`. `client` is the fixture above. Pytest sees the argument name, calls the `client` fixture, and passes the result in. You do not call the fixture yourself.

`"""A webhook signed with our secret is accepted."""`
The docstring is for humans. It says what a pass is supposed to prove. Pytest prints it when a test fails if you use certain flags; the comments below are the main guide.

`# Arrange`
The three comments are the shape to copy: Arrange (set the scene), Act (do the one thing), Assert (check the outcome).

`body = { ... }`
This is a Python dict standing in for Twitch's JSON. The reward title is `Not A Real Reward` so the test does not start the camera filter, the Pokémon catch, or the archiver.

`raw = json.dumps(body).encode("utf-8")`
Twitch signs the raw bytes of the body, not a Python dict. `json.dumps` makes a string. `.encode("utf-8")` makes bytes. The test sends these same bytes. If you built a new JSON later, the signature would not match.

`headers = signed_headers(raw, message_id="msg-valid")`
`signed_headers` is the helper at the top of the file. It fills in the four Twitch headers: message id, a fresh timestamp, the HMAC signature, and the message type `notification`. The signature is `sha256=` plus HMAC-SHA256 of `message id + timestamp + raw body`, using `TEST_SECRET`. That is the same formula as `signature_matches` in `Server.py`. `message_id="msg-valid"` is just a label so this message is not confused with another test.

`response = client.post("/webhook", data=raw, headers=headers)`
This is the Act. It calls `webhook()` as if Twitch posted to the server. `data=raw` sends the bytes we signed. No port is opened.

`assert response.status_code == 200`
This is the Assert. `assert` means "stop the test if this is false." Status 200 means the server accepted the signed message. If the secret, the byte order, or the route is wrong, this line fails and pytest prints both numbers.

The next test, `test_invalid_signature_is_rejected`, copies this setup and then overwrites the signature with junk. Same body, bad signature, status 403, and the event feed stays empty. Read that one second. The contrast is the whole point of the signature check.

## How to write a new test

1. Pick an item from `tests.txt`.
2. Copy the test above into `tests/test_examples.py` and rename it. Names read like a sentence: `test_stale_timestamp_is_rejected`.
3. Change the Arrange so the scene matches the idea. Use `monkeypatch` when the idea says to mock.
4. Keep a single Act.
5. Assert the expected status, JSON, or function call. One behavior per test is enough.
6. Run `pytest -v` and read the bottom line.

Do not point a test at real Twitch or a live OBS. If a test needs a file, use pytest's `tmp_path` (a temp folder that goes away after the test) the way the credits and clip tests do.
