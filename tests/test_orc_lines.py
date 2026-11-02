"""Orc clip voice lines: lines.js matches the mp3s, and the rank map is backwards.

The widget (widgets/orc-clip/orc.js, findLine) picks the line. These tests
do not run the browser. They check the list the browser reads.
"""

import json
import re
from pathlib import Path

import pytest

import Server

ROOT = Path(__file__).resolve().parents[1]
LINES_JS = ROOT / "widgets" / "orc-clip" / "lines.js"
AUDIO = ROOT / "widgets" / "orc-clip" / "audio"
README = ROOT / "widgets" / "orc-clip" / "README.md"


@pytest.fixture
def client():
    Server.app.config["TESTING"] = True
    return Server.app.test_client()


def load_lines(path):
    """Read lines.js. Full-line // comments and trailing commas are allowed."""

    raw = path.read_text(encoding="utf-8")
    raw = re.sub(r"^\s*//.*$", "", raw, flags=re.M)
    body = raw.split("=", 1)[1].rsplit(";", 1)[0]
    body = re.sub(r",\s*([\]}])", r"\1", body)
    data = json.loads(body)
    if not isinstance(data, dict):
        raise AssertionError("ORC_LINES should be an object")
    return data


def test_voice_lines_match_ranks_and_audio_files():
    """WoW1 is WoW #10, Twitch1 is Twitch #5, and every file on disk is listed."""

    # Proves: a renamed mp3 or a flipped rank fails here instead of on stream.
    # voice_end_s is after the orc starts talking, which is what the countdown uses.

    lines = load_lines(LINES_JS)
    assert set(lines) == {"wow", "twitch"}

    wow = {row["file"]: row for row in lines["wow"]}
    twitch = {row["file"]: row for row in lines["twitch"]}
    assert set(wow) == {f"WoW{i}.mp3" for i in range(1, 11)}
    assert set(twitch) == {f"Twitch{i}.mp3" for i in range(1, 6)}

    for number in range(1, 11):
        row = wow[f"WoW{number}.mp3"]
        assert row["rank"] == 11 - number
        assert row["text"].strip()
        assert row["voice_end_s"] > row["voice_start_s"] >= 0
    for number in range(1, 6):
        row = twitch[f"Twitch{number}.mp3"]
        assert row["rank"] == 6 - number
        assert row["text"].strip()
        assert row["voice_end_s"] > row["voice_start_s"] >= 0

    raw_text = LINES_JS.read_text(encoding="utf-8")
    assert "Loqtar" not in raw_text
    assert "Lok'tar" in raw_text

    listed = [row["file"] for row in lines["wow"] + lines["twitch"]]
    on_disk = {path.name for path in AUDIO.glob("*.mp3")}
    assert set(listed) == on_disk
    assert len(listed) == len(set(listed))
    for name in listed:
        assert (AUDIO / name).stat().st_size > 1000


def test_widgets_route_serves_an_orc_line(client, monkeypatch):
    """GET /widgets/orc-clip/audio/WoW10.mp3 returns that mp3."""

    # Proves: the ranked line is reachable at the URL the widget plays.
    # WoW10.mp3 is the WoW #1 line.

    monkeypatch.delenv("WIDGETS_DIR", raising=False)

    # Act
    page = client.get("/widgets/orc-clip/lines.js")
    audio = client.get("/widgets/orc-clip/audio/WoW10.mp3")

    # Assert
    assert page.status_code == 200
    assert b"WoW10.mp3" in page.data
    assert audio.status_code == 200
    assert audio.mimetype == "audio/mpeg"
    assert len(audio.data) > 1000


def test_readme_credits_the_music_bed():
    """The widget README names the drums under the voice lines, not Clarion."""

    text = README.read_text(encoding="utf-8")
    assert "Clarion" not in text
    assert "Scott Buckley" not in text
    assert "Infinita08" in text
    assert "459561" in text
    assert "CC0" in text
