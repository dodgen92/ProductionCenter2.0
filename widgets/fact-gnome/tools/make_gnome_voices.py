"""Pre-record the Fact Gnome's lines with Kokoro (free, runs on your PC).

Run this OFF-STREAM whenever you change facts/facts.js:
    python make_gnome_voices.py
    python make_gnome_voices.py --voice af_heart --speed 1.1

It reads widgets/fact-gnome/facts/facts.js, makes one .wav per fact in
widgets/fact-gnome/voice/, and writes voice/voices.js, which maps each
fact's exact text to its audio file so the gnome can play it.
Facts that already have audio are skipped; audio for deleted facts is removed.
Needs its own venv (Python 3.12):  pip install kokoro soundfile numpy
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

GNOME_DIR = Path(__file__).resolve().parent.parent  # widgets/fact-gnome
FACTS_FILE = GNOME_DIR / "facts" / "facts.js"
VOICE_DIR = GNOME_DIR / "voice"
SAMPLE_RATE = 24000  # Kokoro's output rate


def read_facts(path=FACTS_FILE):
    """Return the list of fact strings from facts.js."""
    text = path.read_text(encoding="utf-8")
    start = text.index("[")
    end = text.rindex("]")
    body = text[start + 1:end]
    # every "double quoted" string in the array, with JS escapes undone
    return [json.loads(m) for m in re.findall(r'"(?:[^"\\]|\\.)*"', body)]


def file_name(fact, voice, speed):
    """Same fact + voice + speed -> same file name, so reruns skip done work."""
    key = f"{voice}|{speed}|{fact}".encode("utf-8")
    return hashlib.sha1(key).hexdigest()[:12] + ".wav"


def write_manifest(mapping, voice_dir=VOICE_DIR):
    """voices.js: window.GNOME_VOICES = {"fact text": "voice/abc.wav", ...}"""
    js = "// Made by tools/make_gnome_voices.py. Don't edit by hand; rerun the script.\n"
    js += "window.GNOME_VOICES = " + json.dumps(mapping, indent=1, ensure_ascii=False) + ";\n"
    (voice_dir / "voices.js").write_text(js, encoding="utf-8")


def build(facts, speak, voice, speed, voice_dir=VOICE_DIR):
    """Make missing audio, delete stale audio, write the manifest.
    speak(text) must return a 1-D float array of audio samples."""
    import numpy as np
    import soundfile as sf

    voice_dir.mkdir(parents=True, exist_ok=True)
    mapping, made = {}, 0
    for i, fact in enumerate(facts, 1):
        name = file_name(fact, voice, speed)
        mapping[fact] = f"voice/{name}"
        out = voice_dir / name
        if out.is_file():
            continue
        print(f"[{i}/{len(facts)}] {fact[:60]}...")
        sf.write(out, np.asarray(speak(fact), dtype="float32"), SAMPLE_RATE)
        made += 1

    keep = {Path(p).name for p in mapping.values()}
    removed = 0
    for old in voice_dir.glob("*.wav"):
        if old.name not in keep:
            old.unlink()
            removed += 1

    write_manifest(mapping, voice_dir)
    print(f"Done: {made} new, {len(facts) - made} already there, {removed} old removed.")
    return mapping


def kokoro_speaker(voice, speed):
    import numpy as np
    from kokoro import KPipeline

    lang = voice[0]  # af_/am_ = American 'a', bf_/bm_ = British 'b'
    pipe = KPipeline(lang_code=lang)

    def speak(text):
        chunks = [audio for _, _, audio in pipe(text, voice=voice, speed=speed)]
        return np.concatenate([np.asarray(c) for c in chunks])

    return speak


def main():
    parser = argparse.ArgumentParser(description="Pre-record Fact Gnome lines with Kokoro.")
    parser.add_argument("--voice", default="af_bella", help="Kokoro voice, e.g. af_bella, af_heart, bf_emma")
    parser.add_argument("--speed", type=float, default=1.1, help="1.0 = normal")
    args = parser.parse_args()

    facts = read_facts()
    print(f"{len(facts)} facts in {FACTS_FILE}")
    build(facts, kokoro_speaker(args.voice, args.speed), args.voice, args.speed)


if __name__ == "__main__":
    main()
