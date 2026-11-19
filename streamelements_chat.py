"""YouTube and Kick chat from StreamElements Astro.

Flask opens the websocket. The widget only polls /wow-chat/feed, so the
StreamElements token never goes to OBS. Twitch chat stays on the widget's
own IRC connection. Messages with provider twitch are dropped here so a
line does not show twice.

Astro docs: https://docs.streamelements.com/websockets
Topic: https://docs.streamelements.com/websockets/topics/channel-chat
"""

import json
import os
import threading
import time
import uuid
from collections import deque
from urllib.parse import urlencode

import websocket
from websocket import ABNF

# Trailing slash matches the reconnect URL in the Astro docs.
ASTRO_URL = "wss://astro.streamelements.com/"
TOPIC = "channel.chat"
# Twitch is already on IRC. x is a real provider, and this widget does not draw it.
RELAY_PROVIDERS = {"youtube", "kick"}
TOKEN_TYPES = {"jwt", "apikey", "oauth2"}
# A short secret would punch holes in ordinary words. Real JWTs are much longer.
MIN_SECRET_LENGTH = 8
FEED_MAX = 50
REMEMBER_MAX = 300

FEED = deque(maxlen=FEED_MAX)
FEED_ID = 0
_seen_ids = deque()
_seen_set = set()
_deleted_ids = deque()
_deleted_set = set()
_lock = threading.Lock()
_client = None


def reset_feed():
    """Empty the widget feed. Tests call this so one case cannot leak into the next."""

    global FEED_ID
    with _lock:
        FEED_ID = 0
        FEED.clear()
        _seen_ids.clear()
        _seen_set.clear()
        _deleted_ids.clear()
        _deleted_set.clear()


def split_list(value):
    """Comma-separated env value. Blank pieces are dropped."""

    return [part.strip() for part in (value or "").split(",") if part.strip()]


def parse_accounts(token_value, room_value):
    """One account per token.

    The Astro docs say a token is for the platform account you copied it from.
    They do not say one token covers every linked platform, so a comma-separated
    list is allowed. One channel id is reused for every token. Several ids pair
    up with the tokens in order. Extra tokens subscribe with no room.
    """

    tokens = split_list(token_value)
    rooms = split_list(room_value)
    accounts = []
    for index, token in enumerate(tokens):
        if len(rooms) == 1:
            room = rooms[0]
        elif index < len(rooms):
            room = rooms[index]
        else:
            room = ""
        accounts.append({"token": token, "room": room})
    return accounts


def normalize_token_type(value):
    """jwt, apikey, or oauth2. Anything else, including blank, is jwt."""

    kind = (value or "").strip().lower()
    if kind in TOKEN_TYPES:
        return kind
    return "jwt"


def _remember(bucket, order, key):
    if not key or key in bucket:
        return
    if len(order) >= REMEMBER_MAX:
        old = order.popleft()
        bucket.discard(old)
    order.append(key)
    bucket.add(key)


def _drop_where(predicate):
    kept = [item for item in FEED if not predicate(item)]
    FEED.clear()
    FEED.extend(kept)


def _store(event):
    """Save one relay event. Caller holds _lock. False means the widget should not see it."""

    global FEED_ID
    provider = event.get("provider") or ""
    kind = event.get("event")

    if kind == "message":
        message_id = event.get("message_id") or ""
        key = provider + ":" + message_id
        if message_id and (key in _deleted_set or key in _seen_set):
            return False
        if message_id:
            _remember(_seen_set, _seen_ids, key)
    elif kind == "message_deleted":
        message_id = event.get("message_id") or ""
        key = provider + ":" + message_id
        _remember(_deleted_set, _deleted_ids, key)
        _drop_where(
            lambda item: item.get("event") == "message"
            and item.get("provider") == provider
            and item.get("message_id") == message_id
        )
    elif kind == "user_cleared":
        user_id = event.get("user_id") or ""
        login = (event.get("login") or "").lower()

        def drop_user(item):
            if item.get("event") != "message" or item.get("provider") != provider:
                return False
            if user_id and item.get("user_id") == user_id:
                return True
            if login and (item.get("login") or "").lower() == login:
                return True
            return False

        _drop_where(drop_user)
    elif kind == "chat_cleared":
        _drop_where(
            lambda item: item.get("event") == "message" and item.get("provider") == provider
        )

    FEED_ID += 1
    stored = dict(event)
    stored["seq"] = FEED_ID
    FEED.append(stored)
    return True


def redact_text(text, secrets):
    cleaned = text
    for secret in sorted((secrets or ()), key=len, reverse=True):
        if isinstance(secret, str) and len(secret) >= MIN_SECRET_LENGTH and secret in cleaned:
            cleaned = cleaned.replace(secret, "[redacted]")
    return cleaned


def redact_value(value, secrets):
    if isinstance(value, str):
        return redact_text(value, secrets)
    if isinstance(value, list):
        return [redact_value(item, secrets) for item in value]
    if isinstance(value, dict):
        return {key: redact_value(item, secrets) for key, item in value.items()}
    return value


def censor_text(text):
    """Same whole-word filter the server uses for other viewer text."""

    import Server

    try:
        return Server.censor_viewer_text(text or "")
    except Exception as exc:
        print(f"[Astro] Word filter failed: {type(exc).__name__}")
        return text or ""


def message_text(data):
    """The line to draw. Fragment text covers a message that arrived without `text`."""

    text = data.get("text")
    if isinstance(text, str) and text:
        return text
    fragments = data.get("fragments")
    if not isinstance(fragments, list):
        return text if isinstance(text, str) else ""
    parts = []
    for fragment in fragments:
        if not isinstance(fragment, dict):
            continue
        piece = fragment.get("text")
        if isinstance(piece, str):
            parts.append(piece)
    return "".join(parts)


def _author(data):
    author = data.get("author") if isinstance(data.get("author"), dict) else {}
    login = author.get("login") if isinstance(author.get("login"), str) else ""
    name = author.get("name") if isinstance(author.get("name"), str) else ""
    user_id = author.get("id") if isinstance(author.get("id"), str) else ""
    roles = author.get("roles") if isinstance(author.get("roles"), list) else []
    roles = [role for role in roles if isinstance(role, str)]
    return login, name, user_id, roles


def normalize_chat(data, censor):
    """Turn one channel.chat `data` object into a widget event, or None to skip it.

    `censor` is called only for YouTube and Kick message text. Twitch returns
    before that, so this path does not touch the IRC lines.
    """

    if not isinstance(data, dict):
        return None
    provider = data.get("provider")
    if not isinstance(provider, str):
        return None
    provider = provider.strip().lower()
    if provider not in RELAY_PROVIDERS:
        return None

    kind = data.get("event")
    if kind == "message":
        login, name, user_id, roles = _author(data)
        text = censor(message_text(data))
        message_kind = data.get("kind") if isinstance(data.get("kind"), str) and data.get("kind") else "text"
        message_id = data.get("id") if isinstance(data.get("id"), str) else ""
        return {
            "event": "message",
            "provider": provider,
            "message_id": message_id,
            "user_id": user_id,
            "login": login,
            "name": name or login or "Someone",
            "text": text,
            "kind": message_kind,
            "roles": roles,
        }
    if kind == "message_deleted":
        message_id = data.get("message_id") if isinstance(data.get("message_id"), str) else ""
        if not message_id:
            return None
        return {
            "event": "message_deleted",
            "provider": provider,
            "message_id": message_id,
        }
    if kind == "user_cleared":
        user = data.get("user") if isinstance(data.get("user"), dict) else {}
        user_id = user.get("id") if isinstance(user.get("id"), str) else ""
        login = user.get("login") if isinstance(user.get("login"), str) else ""
        if not user_id and not login:
            return None
        return {
            "event": "user_cleared",
            "provider": provider,
            "user_id": user_id,
            "login": login,
        }
    if kind == "chat_cleared":
        return {"event": "chat_cleared", "provider": provider}
    return None


def feed_since(since):
    """Lines newer than `since`, for GET /wow-chat/feed."""

    try:
        cursor = int(since)
    except (TypeError, ValueError):
        cursor = 0
    if cursor < 0:
        cursor = 0
    with _lock:
        messages = [dict(item) for item in FEED if item.get("seq", 0) > cursor]
        last = FEED_ID
    return {"last_seq": last, "messages": messages}


class AstroClient:
    """One Astro websocket. Subscribe once per token after welcome.

    A reconnect message carries a one-use token. The next socket uses it and
    does not subscribe again. Any other drop waits and subscribes from scratch.
    The wait starts at 1 second and stops growing at 30.
    """

    def __init__(self, accounts, token_type="jwt", enabled=True, reason=""):
        self.accounts = list(accounts or [])
        self.token_type = token_type if token_type in TOKEN_TYPES else "jwt"
        self.enabled = bool(enabled) and bool(self.accounts)
        self.reason = reason
        self.reconnect_token = ""
        self._skip_subscribe = False
        self.backoff = 1
        self.recv_timeout = 1
        self.connect_timeout = 15
        self._ws = None
        self._stop = threading.Event()
        self._thread = None

    def __repr__(self):
        return f"AstroClient(tokens={len(self.accounts)}, enabled={self.enabled})"

    @classmethod
    def from_env(cls):
        accounts = parse_accounts(
            os.getenv("STREAMELEMENTS_TOKEN"),
            os.getenv("STREAMELEMENTS_CHANNEL_ID"),
        )
        raw_type = (os.getenv("STREAMELEMENTS_TOKEN_TYPE") or "").strip().lower()
        token_type = normalize_token_type(raw_type)
        switch = (os.getenv("STREAMELEMENTS_ENABLED") or "").strip().lower()
        if switch in {"0", "false", "no", "off"}:
            return cls(accounts, token_type, enabled=False, reason="switch")
        if not accounts:
            return cls([], token_type, enabled=False, reason="no-token")
        if raw_type and raw_type not in TOKEN_TYPES:
            print("[Astro] STREAMELEMENTS_TOKEN_TYPE was not jwt, apikey, or oauth2. Using jwt.")
        return cls(accounts, token_type, enabled=True, reason="")

    def secrets(self, extra=()):
        found = [account.get("token") or "" for account in self.accounts]
        if self.reconnect_token:
            found.append(self.reconnect_token)
        found.extend(extra)
        return found

    def redact(self, value, extra=()):
        return redact_text(str(value), self.secrets(extra))

    def connection_url(self):
        if not self.reconnect_token:
            return ASTRO_URL
        query = urlencode({"reconnect_token": self.reconnect_token})
        return ASTRO_URL + "?" + query

    def subscribe_payload(self, account):
        data = {
            "topic": TOPIC,
            "token": account.get("token") or "",
            "token_type": self.token_type,
        }
        room = account.get("room") or ""
        if room:
            data["room"] = room
        return {
            "type": "subscribe",
            "nonce": str(uuid.uuid4()),
            "data": data,
        }

    def start(self):
        """Open the socket on a daemon thread. No token, or the switch off, does nothing."""

        if self._thread is not None and self._thread.is_alive():
            return True
        if not self.enabled:
            if self.reason == "switch":
                print("[Astro] STREAMELEMENTS_ENABLED is off. Skipping YouTube and Kick chat.")
            else:
                print("[Astro] No STREAMELEMENTS_TOKEN. Skipping YouTube and Kick chat.")
            return False
        self._stop.clear()
        self._thread = threading.Thread(
            target=self.run,
            name="streamelements-astro",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        ws = self._ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def take_delay(self):
        delay = self.backoff
        if delay > 30:
            delay = 30
        self.backoff = self.backoff * 2
        if self.backoff > 30:
            self.backoff = 30
        return delay

    def run(self):
        print(f"[Astro] YouTube and Kick chat starting ({len(self.accounts)} token(s)).")
        while not self._stop.is_set():
            self._connect_and_read()
            if self._stop.is_set():
                break
            if self.reconnect_token:
                print("[Astro] Server asked for a reconnect.")
                continue
            delay = self.take_delay()
            print(f"[Astro] Disconnected. Reconnecting in {delay:g}s.")
            if self._stop.wait(delay):
                break
        print("[Astro] YouTube and Kick chat stopped.")

    def _connect_and_read(self):
        used_reconnect = bool(self.reconnect_token)
        url = self.connection_url()
        reconnect_secret = self.reconnect_token
        self.reconnect_token = ""
        self._skip_subscribe = used_reconnect
        try:
            ws = self._open_socket(url)
        except Exception as exc:
            self._skip_subscribe = False
            print(f"[Astro] Connection failed: {self.redact(exc, extra=[reconnect_secret])}")
            return

        self._ws = ws
        try:
            while not self._stop.is_set():
                try:
                    frame = ws.recv_frame()
                except websocket.WebSocketTimeoutException:
                    continue
                except Exception as exc:
                    print(f"[Astro] Socket closed: {self.redact(exc, extra=[reconnect_secret])}")
                    return
                outcome = self.handle_frame(ws, frame)
                if outcome in ("reconnect", "close"):
                    return
        finally:
            self._skip_subscribe = False
            try:
                ws.close()
            except Exception:
                pass
            if self._ws is ws:
                self._ws = None

    def _open_socket(self, url):
        ws = websocket.create_connection(url, timeout=self.connect_timeout)
        ws.settimeout(self.recv_timeout)
        return ws

    def handle_frame(self, ws, frame):
        opcode = getattr(frame, "opcode", None)
        data = getattr(frame, "data", b"")
        if opcode == ABNF.OPCODE_PING:
            if isinstance(data, str):
                data = data.encode("utf-8")
            if not isinstance(data, (bytes, bytearray)):
                data = b""
            ws.pong(data)
            return "pong"
        if opcode == ABNF.OPCODE_PONG:
            return "pong"
        if opcode == ABNF.OPCODE_CLOSE:
            return "close"
        if opcode != ABNF.OPCODE_TEXT:
            return "ignored"
        if isinstance(data, bytes):
            raw = data.decode("utf-8", errors="replace")
        else:
            raw = data if isinstance(data, str) else ""
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            print("[Astro] Ignored a message that was not JSON.")
            return "ignored"
        return self.handle_message(ws, message)

    def handle_message(self, ws, message):
        if not isinstance(message, dict):
            return "ignored"
        kind = message.get("type")
        if kind == "welcome":
            self.backoff = 1
            if self._skip_subscribe:
                self._skip_subscribe = False
                print("[Astro] Reconnected. Subscriptions were restored.")
                return "welcome-restored"
            self.send_subscribes(ws)
            return "welcome"
        if kind == "response":
            self._log_response(message)
            return "response"
        if kind == "reconnect":
            data = message.get("data") if isinstance(message.get("data"), dict) else {}
            token = data.get("reconnect_token") if isinstance(data.get("reconnect_token"), str) else ""
            token = token.strip()
            if not token:
                print("[Astro] Reconnect message had no token.")
                return "ignored"
            self.reconnect_token = token
            return "reconnect"
        if kind == "message":
            if message.get("topic") != TOPIC:
                return "ignored"
            return self._relay_data(message.get("data"))
        if isinstance(kind, str) and kind:
            print("[Astro] Ignored an unknown message type.")
        return "ignored"

    def send_subscribes(self, ws):
        if ws is None:
            return
        for index, account in enumerate(self.accounts):
            if index:
                # Astro allows one subscribe command per 100ms.
                time.sleep(0.11)
            ws.send(json.dumps(self.subscribe_payload(account)))
        print(f"[Astro] Asked for channel.chat ({len(self.accounts)} token(s)).")

    def _log_response(self, message):
        error = message.get("error") if isinstance(message.get("error"), str) else ""
        data = message.get("data") if isinstance(message.get("data"), dict) else {}
        detail = data.get("message") if isinstance(data.get("message"), str) else ""
        detail = self.redact(detail)
        if error:
            print(f"[Astro] {error}: {detail}")
            return
        if detail:
            print(f"[Astro] {detail}")

    def _relay_data(self, data):
        event = normalize_chat(data, censor_text)
        if event is None:
            return "ignored"
        cleaned = redact_value(event, self.secrets())
        with _lock:
            stored = _store(cleaned)
        return "relay" if stored else "ignored"


def start():
    """Start the client from .env. Safe to call when the token is missing."""

    global _client
    _client = AstroClient.from_env()
    return _client.start()


def stop():
    if _client is not None:
        _client.stop()
