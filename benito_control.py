"""Who may command Benito, and which chat line is which keybind.

The clock is a callable so tests can move time without sleeping.
Default mode is all of chat. A cheer of exactly BENITO_CONTROL_BITS
(default 107) gives that viewer exclusive control for BENITO_CONTROL_SECONDS
(default 600). Anyone else who cheers that amount waits in a FIFO queue.
When the queue is empty, chat as a whole can command him again.

This module does not press keys and does not talk to Twitch.
The server does that after it reads the result.
"""

import os
import threading
import time
from collections import deque


# Longer lines are listed first so a future prefix match cannot
# treat "!rejuv party2" as "!rejuv". Matching today is exact.
# command, keybind, target
BENITO_KEYBINDS = (
    ("!rejuv party2", "Alt+2", "party2"),
    ("!rejuv party3", "Alt+3", "party3"),
    ("!rejuv party4", "Alt+4", "party4"),
    ("!rejuv me", "Shift+1", "Benito"),
    ("!regrowth me", "Shift+2", "Benito"),
    ("!healtouch me", "Shift+3", "Benito"),
    ("!motw me", "Shift+6", "Benito"),
    ("!rejuv", "1", "Remy"),
    ("!regrowth", "2", "Remy"),
    ("!healtouch", "3", "Remy"),
    ("!moonfire", "4", "Remy's target"),
    ("!wrath", "5", "Remy's target"),
    ("!motw", "6", "Remy"),
    ("!interact", "Shift+4", ""),
    ("!bear", "Shift+5", "Benito"),
)

KICK_COMMAND = "!benitokick"


def _env_int(name, default):
    try:
        value = int(os.getenv(name) or default)
    except (TypeError, ValueError):
        return int(default)
    if value < 1:
        return int(default)
    return value


def control_bits():
    return _env_int("BENITO_CONTROL_BITS", 107)


def control_seconds():
    return _env_int("BENITO_CONTROL_SECONDS", 600)


def span_words(seconds):
    """600 becomes '10 minutes'. Anything else stays in seconds."""

    seconds = int(seconds)
    if seconds > 0 and seconds % 60 == 0:
        minutes = seconds // 60
        unit = "minute" if minutes == 1 else "minutes"
        return f"{minutes} {unit}"
    unit = "second" if seconds == 1 else "seconds"
    return f"{seconds} {unit}"


def _mention(person):
    name = (person.get("login") or person.get("user") or "friend").strip().lstrip("@")
    return "@" + (name or "friend")


def _notice(reason, person, seconds, queue, chat):
    mode = "all" if reason == "open" else "exclusive"
    return {
        "reason": reason,
        "mode": mode,
        "user": person.get("user") or "",
        "login": person.get("login") or "",
        "user_id": person.get("user_id") or "",
        "seconds": seconds,
        "queue": queue,
        "chat": chat,
    }


def normalized_chat(text):
    return " ".join((text or "").split()).lower()


def is_kick_command(text):
    return normalized_chat(text) == KICK_COMMAND


def parse_command(text):
    """Return command, keybind, and target, or None when it is not a command."""

    cleaned = normalized_chat(text)
    for command, keybind, target in BENITO_KEYBINDS:
        if cleaned == command:
            return {"command": command, "keybind": keybind, "target": target}
    return None


class BenitoControl:
    """Exclusive control, the waiting line, and the open-chat default."""

    def __init__(self, clock=None):
        self.clock = clock or time.monotonic
        self.holder = None
        self.queue = deque()
        self.lock = threading.Lock()

    def poll(self):
        """End a turn whose time is up, then start the next person."""

        with self.lock:
            return self._expire_locked()

    def cheer(self, user_id, user, login, bits, anonymous=False):
        """Grant a turn, or queue one, when the bit amount is exact."""

        with self.lock:
            notices = self._expire_locked()
            if anonymous:
                return notices
            try:
                amount = int(bits)
            except (TypeError, ValueError):
                return notices
            if amount != control_bits():
                return notices
            uid = str(user_id or "")
            if not uid:
                return notices
            person = {"user_id": uid, "user": user or "", "login": login or ""}
            if self.holder is None:
                notices.append(self._start_locked(person))
                return notices
            self.queue.append(person)
            chat = (
                f"{_mention(person)}, Benito is with someone else. "
                "The Earth Mother has your place in line."
            )
            notices.append(_notice(
                "queued",
                person,
                control_seconds(),
                len(self.queue),
                chat,
            ))
            return notices

    def kick(self):
        """End the current turn now. Caller must already know this is the broadcaster.

        If the turn already expired, this only advances the queue the normal way.
        It does not also skip the person who just inherited the chair.
        """

        with self.lock:
            if self.holder is not None and self.clock() < self.holder["until"]:
                return self._end_locked("kick")
            return self._expire_locked()

    def allows(self, user_id):
        """True for everyone when chat is open, or for the current holder."""

        with self.lock:
            if self.holder is None:
                return True
            return str(user_id or "") == self.holder["user_id"]

    def _start_locked(self, person):
        seconds = control_seconds()
        self.holder = {
            "user_id": person["user_id"],
            "user": person["user"],
            "login": person["login"],
            "until": self.clock() + seconds,
        }
        chat = (
            f"{_mention(person)}, Benito is yours for {span_words(seconds)}! "
            "Earth Mother guide your paws."
        )
        return _notice("start", person, seconds, len(self.queue), chat)

    def _end_locked(self, reason):
        ended = self.holder
        self.holder = None
        person = {
            "user_id": ended["user_id"],
            "user": ended["user"],
            "login": ended["login"],
        }
        chat = f"{_mention(person)}, your time is up. Earth Mother calls him back."
        notices = [_notice(reason, person, 0, len(self.queue), chat)]
        if self.queue:
            nxt = self.queue.popleft()
            notices.append(self._start_locked(nxt))
        else:
            notices.append(_notice(
                "open",
                {"user_id": "", "user": "", "login": ""},
                0,
                0,
                "Benito is listening to all of chat again.",
            ))
        return notices

    def _expire_locked(self):
        notices = []
        guard = len(self.queue) + 1
        while (
            guard > 0
            and self.holder is not None
            and self.clock() >= self.holder["until"]
        ):
            guard -= 1
            notices.extend(self._end_locked("end"))
        return notices
