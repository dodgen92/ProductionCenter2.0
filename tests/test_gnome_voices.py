"""Tests for make_gnome_voices.py with a fake Kokoro (no model needed)."""
import hashlib
import importlib.util
import json
import re
import struct
import sys
import tempfile
import types
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


def _old_cache_name(fact, voice, speed):
    """The name from before pitch, ghoul, and spoken.js existed."""

    key = f"{voice}|{speed}|{fact}".encode("utf-8")
    return hashlib.sha1(key).hexdigest()[:12] + ".wav"


def test_default_filename_matches_old_cache_key():
    fact, voice, speed = "Hello there.", "af_bella", 1.1
    old = _old_cache_name(fact, voice, speed)
    assert m.file_name(fact, voice, speed) == old
    assert m.file_name(fact, voice, speed, pitch=0, ghoul=False, spoken=None) == old
    # Saying the fact with no markup is the same recording as before.
    assert m.file_name(fact, voice, speed, spoken=fact) == old


def test_pitch_ghoul_and_spoken_change_the_file_hash():
    fact, voice, speed = "Hello there.", "af_bella", 1.1
    base = m.file_name(fact, voice, speed)
    higher = m.file_name(fact, voice, speed, pitch=2)
    assert higher != base
    assert higher == m.file_name(fact, voice, speed, pitch=2.0)
    ghoul = m.file_name(fact, voice, speed, pitch=-4, ghoul=True)
    assert ghoul != base
    assert ghoul != m.file_name(fact, voice, speed, pitch=-4, ghoul=False)
    marked = "Hello [there](+1)."
    assert m.file_name(fact, voice, speed, spoken=marked) != base
    assert m.file_name(fact, voice, speed, spoken=marked) != m.file_name(
        fact, voice, speed, spoken=marked + "!"
    )


def test_chosen_pitch_defaults():
    assert m.chosen_pitch(None, False) == 0
    assert m.chosen_pitch(None, True) == -4
    assert m.chosen_pitch(2, True) == 2
    assert m.chosen_pitch(0, True) == 0


def test_default_build_audio_is_unchanged():
    """No flags: same samples, same rate, same file name as the old cache."""

    np = _audio_libs()
    import soundfile as sf

    y = np.linspace(-0.4, 0.6, 1800, dtype=np.float32)
    with tempfile.TemporaryDirectory() as d:
        vd = Path(d) / "voice"
        m.build(["hello"], lambda _text: y, "af_bella", 1.1, vd)
        data, rate = sf.read(next(vd.glob("*.wav")))
        assert rate == m.SAMPLE_RATE
        assert np.allclose(data, y, atol=1e-4)
        assert (vd / _old_cache_name("hello", "af_bella", 1.1)).is_file()


def _loudest_hz(samples, sr):
    import numpy as np

    window = np.hanning(len(samples))
    spec = np.abs(np.fft.rfft(np.asarray(samples) * window))
    spec[0] = 0
    return int(np.argmax(spec)) * sr / len(samples)


def test_pitch_shift_keeps_length_and_moves_the_tone():
    np = _audio_libs()
    pytest.importorskip("scipy")
    sr = m.SAMPLE_RATE
    freq = 220.0
    t = np.arange(sr) / sr
    y = (0.4 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    out = m.shift_pitch(y, 2, sr)
    assert abs(len(out) - len(y)) / len(y) < 0.02
    expect = freq * 2 ** (2 / 12)
    got = _loudest_hz(out, sr)
    assert abs(got - expect) / expect < 0.03


def test_ghoul_does_not_clip_and_keeps_sample_rate():
    np = _audio_libs()
    pytest.importorskip("scipy")
    import soundfile as sf

    sr = m.SAMPLE_RATE
    t = np.arange(int(sr * 0.35)) / sr
    hot = (0.95 * np.sin(2 * np.pi * 160 * t)).astype(np.float32)
    # --ghoul with no --pitch uses the lower voice, then grit and echo.
    shaped = m.shape_audio(hot, pitch=m.chosen_pitch(None, True), ghoul=True, sr=sr)
    assert shaped.ndim == 1
    assert np.max(np.abs(shaped)) <= 1.0
    with tempfile.TemporaryDirectory() as d:
        vd = Path(d) / "voice"
        m.build(["line"], lambda _text: hot, "af_bella", 1.1, vd, pitch=-4, ghoul=True)
        data, rate = sf.read(next(vd.glob("*.wav")))
        assert rate == sr
        assert np.max(np.abs(data)) <= 1.0
        assert (vd / m.file_name("line", "af_bella", 1.1, pitch=-4, ghoul=True)).is_file()


def test_pitch_change_regenerates_and_drops_the_old_wav():
    np = _audio_libs()
    pytest.importorskip("scipy")

    def speak(_text):
        return np.zeros(400, dtype=np.float32)

    with tempfile.TemporaryDirectory() as d:
        vd = Path(d) / "voice"
        m.build(["a"], speak, "af_bella", 1.1, vd)
        first = {p.name for p in vd.glob("*.wav")}
        calls = []
        m.build(["a"], lambda text: calls.append(text) or speak(text), "af_bella", 1.1, vd, pitch=2)
        assert calls == ["a"]
        second = {p.name for p in vd.glob("*.wav")}
        assert first.isdisjoint(second)
        assert len(second) == 1
        calls.clear()
        m.build(["a"], lambda text: calls.append(text) or speak(text), "af_bella", 1.1, vd, pitch=2)
        assert calls == []


def test_spoken_override_is_said_and_manifest_stays_plain():
    np = _audio_libs()
    calls = []

    def speak(text):
        calls.append(text)
        return np.zeros(200, dtype=np.float32)

    facts = ["plain one", "plain two"]
    marked = "plain [one](/wˈʌn/) … [they](+1)"
    with tempfile.TemporaryDirectory() as d:
        vd = Path(d) / "voice"
        mapping = m.build(facts, speak, "af_bella", 1.1, vd, spoken={"plain one": marked, "plain two": "   "})
        assert calls == [marked, "plain two"]
        assert set(mapping) == set(facts)
        js = (vd / "voices.js").read_text(encoding="utf-8")
        saved = json.loads(re.search(r"= (\{.*\});", js, re.S).group(1))
        assert set(saved) == set(facts)
        assert marked not in saved
        assert Path(saved["plain one"]).name == m.file_name("plain one", "af_bella", 1.1, spoken=marked)
        assert Path(saved["plain two"]).name == _old_cache_name("plain two", "af_bella", 1.1)


def test_read_spoken_keeps_markup_quotes_and_allows_a_trailing_comma():
    sample = '''// what she says, not what the bubble shows
window.GNOME_SPOKEN = {
  "plain fact": "Say “well, actually.” [Staats](/stˈæts/) … [they](+1);",
};
'''
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "spoken.js"
        path.write_text(sample, encoding="utf-8")
        spoken = m.read_spoken(path)
        assert spoken == {
            "plain fact": "Say “well, actually.” [Staats](/stˈæts/) … [they](+1);",
        }
        assert m.read_spoken(Path(d) / "missing.js") == {}


def test_shipped_spoken_keys_match_facts():
    facts = m.read_facts()
    spoken = m.read_spoken()
    assert set(spoken) == set(facts)


def _misaki_markup():
    """misaki's English G2P.preprocess, without spacy or a Kokoro model.

    KPipeline (af_ / bf_ voices) calls this G2P on the raw text. preprocess
    is the part that keeps [word](/phonemes/) and [word](+1).
    """

    pytest.importorskip("misaki")
    pytest.importorskip("numpy")
    if "spacy" not in sys.modules:
        try:
            import spacy  # noqa: F401
        except ModuleNotFoundError:
            sys.modules["spacy"] = types.ModuleType("spacy")
    if "num2words" not in sys.modules:
        try:
            import num2words  # noqa: F401
        except ModuleNotFoundError:
            stub = types.ModuleType("num2words")
            stub.num2words = lambda *args, **kwargs: ""
            sys.modules["num2words"] = stub
    try:
        from misaki.en import G2P, LINK_REGEX
    except Exception as exc:
        pytest.skip(f"misaki English G2P could not be loaded: {exc}")
    return G2P, LINK_REGEX


def test_misaki_g2p_accepts_spoken_markup():
    g2p, link_regex = _misaki_markup()
    spoken = m.read_spoken()
    assert spoken
    saw_phoneme = False
    saw_stress = False
    for line in spoken.values():
        result, _tokens, features = g2p.preprocess(line)
        links = link_regex.findall(line)
        assert len(features) == len(links)
        for word, _raw in links:
            assert word in result
        for value in features.values():
            if isinstance(value, str) and value.startswith("/"):
                saw_phoneme = True
            elif isinstance(value, (int, float)):
                saw_stress = True
        for mark in ("…", "—", ";", "“", "”"):
            if mark in line:
                assert mark in result
    assert saw_phoneme
    assert saw_stress
