"""Tests for make_gnome_voices.py with a fake Kokoro (no model needed)."""
import importlib.util
import json
import re
import struct
import tempfile
from pathlib import Path

import pytest

# The script lives under widgets/fact-gnome/tools. That folder name is not a
# package, so load the file. conftest.py already puts the repo root on sys.path.
_SCRIPT = Path(__file__).resolve().parents[1] / "widgets" / "fact-gnome" / "tools" / "make_gnome_voices.py"
_spec = importlib.util.spec_from_file_location("make_gnome_voices", _SCRIPT)
m = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m)

FACTS_JS = '''// comment with "quotes" before the list
window.GNOME_FACTS = [
"Fact one, with 'single' quotes.",
"Fact two \\u2014 escaped.",
];
'''


def _audio_libs():
    """Numpy and soundfile are optional. Skip the generator test if either is missing.

    Kokoro is never imported. speak() is a stand-in.
    """

    np = pytest.importorskip("numpy")
    try:
        import soundfile  # noqa: F401
    except Exception as exc:
        pytest.skip(f"soundfile is unavailable: {exc}")
    return np


def test_read_facts_ignores_comments():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "facts.js"; p.write_text(FACTS_JS, encoding="utf-8")
        assert m.read_facts(p) == ["Fact one, with 'single' quotes.", "Fact two \u2014 escaped."]


def test_build_skips_existing_and_removes_stale():
    np = _audio_libs()

    def fake_speak(text):
        return np.zeros(240, dtype="float32")

    with tempfile.TemporaryDirectory() as d:
        vd = Path(d) / "voice"
        m.build(["a", "b"], fake_speak, "af_bella", 1.1, vd)
        assert len(list(vd.glob("*.wav"))) == 2
        calls = []
        m.build(["a", "c"], lambda t: calls.append(t) or fake_speak(t), "af_bella", 1.1, vd)
        assert calls == ["c"]                      # "a" reused
        assert len(list(vd.glob("*.wav"))) == 2    # "b" removed
        js = (vd / "voices.js").read_text(encoding="utf-8")
        mapping = json.loads(re.search(r"= (\{.*\});", js, re.S).group(1))
        assert set(mapping) == {"a", "c"}
        assert all((vd.parent / f).is_file() for f in mapping.values())


def test_voice_change_regenerates():
    assert m.file_name("a", "af_bella", 1.1) != m.file_name("a", "af_heart", 1.1)


def _tiny_wav():
    """One silent 16-bit sample, so the widgets route can be checked without Kokoro."""

    data = struct.pack("<h", 0)
    return (
        b"RIFF"
        + struct.pack("<I", 36 + len(data))
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, 8000, 16000, 2, 16)
        + b"data"
        + struct.pack("<I", len(data))
        + data
    )


def test_widgets_route_serves_gnome_voice_wav(monkeypatch):
    """GET /widgets/fact-gnome/voice/<file>.wav returns that file."""

    import Server

    monkeypatch.delenv("WIDGETS_DIR", raising=False)
    voice_dir = Server.BASE_DIR / "widgets" / "fact-gnome" / "voice"
    voice_dir.mkdir(parents=True, exist_ok=True)
    wav_path = voice_dir / "_route_check.wav"
    payload = _tiny_wav()
    wav_path.write_bytes(payload)
    try:
        Server.app.config["TESTING"] = True
        response = Server.app.test_client().get("/widgets/fact-gnome/voice/_route_check.wav")
    finally:
        wav_path.unlink(missing_ok=True)
    assert response.status_code == 200
    assert response.data == payload
    assert response.mimetype.startswith("audio/")
    assert response.headers["Cache-Control"] == "no-store"
