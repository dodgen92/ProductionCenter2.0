"""Pre-record the Fact Gnome's lines with Kokoro (free, runs on your PC).

Run this OFF-STREAM whenever you change facts/facts.js or facts/spoken.js:
    python make_gnome_voices.py
    python make_gnome_voices.py --voice af_nicole --pitch 2
    python make_gnome_voices.py --voice af_nicole --ghoul

It reads widgets/fact-gnome/facts/facts.js, makes one .wav per fact in
widgets/fact-gnome/voice/, and writes voice/voices.js, which maps each
fact's exact text to its audio file so the gnome can play it.
facts/spoken.js is optional. If a fact is in there, Kokoro says that
marked-up line; the on-screen text stays the plain fact.
Facts that already have audio are skipped; audio for deleted facts is removed.
Needs its own venv (Python 3.12):  pip install -r requirements-voice.txt
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

GNOME_DIR = Path(__file__).resolve().parent.parent  # widgets/fact-gnome
FACTS_FILE = GNOME_DIR / "facts" / "facts.js"
SPOKEN_FILE = GNOME_DIR / "facts" / "spoken.js"
VOICE_DIR = GNOME_DIR / "voice"
SAMPLE_RATE = 24000  # Kokoro's output rate
# --ghoul with no --pitch: a bit lower, still easy to understand.
GHOUL_PITCH = -4.0


def read_facts(path=FACTS_FILE):
    """Return the list of fact strings from facts.js."""
    text = path.read_text(encoding="utf-8")
    start = text.index("[")
    end = text.rindex("]")
    body = text[start + 1:end]
    # every "double quoted" string in the array, with JS escapes undone
    return [json.loads(m) for m in re.findall(r'"(?:[^"\\]|\\.)*"', body)]


def _strip_js_comments(text):
    """Drop // comments that are not inside a quoted string."""
    out = []
    i = 0
    in_string = False
    escaped = False
    while i < len(text):
        char = text[i]
        if in_string:
            out.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            i += 1
            continue
        if char == '"':
            in_string = True
            out.append(char)
            i += 1
            continue
        if char == "/" and i + 1 < len(text) and text[i + 1] == "/":
            i += 2
            while i < len(text) and text[i] not in "\r\n":
                i += 1
            continue
        out.append(char)
        i += 1
    return "".join(out)


def read_spoken(path=SPOKEN_FILE):
    """Plain fact -> the line Kokoro should say. Missing file means no overrides.

    The file looks like:
        window.GNOME_SPOKEN = { "plain fact": "spoken [word](/phonemes/)", };
    Keys must match facts.js exactly. Values may use Kokoro markup.
    """
    path = Path(path)
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8-sig")
    marker = text.find("GNOME_SPOKEN")
    chunk = text[marker:] if marker >= 0 else text
    start = chunk.find("{")
    end = chunk.rfind("}")
    if start < 0 or end <= start:
        return {}
    body = _strip_js_comments(chunk[start:end + 1])
    # A trailing comma is easy to leave in by hand. JSON rejects it.
    body = re.sub(r",(\s*[}\]])", r"\1", body)
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Couldn't read {path.name}: {exc}. Check the quotes and commas."
        ) from exc
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} should be {{\"fact\": \"spoken line\", ...}}")
    spoken = {}
    for key, value in data.items():
        if isinstance(key, str) and isinstance(value, str) and value.strip():
            spoken[key] = value
    return spoken


def line_to_speak(fact, spoken):
    """Marked-up line when spoken.js has this fact, otherwise the fact itself."""
    if not spoken:
        return fact
    say = spoken.get(fact)
    if isinstance(say, str) and say.strip():
        return say
    return fact


def _pitch_text(pitch):
    """2.0 and 2 should hash the same. 1.5 stays 1.5."""
    text = f"{float(pitch):.4f}".rstrip("0").rstrip(".")
    if text in ("", "-0", "-"):
        return "0"
    return text


def file_name(fact, voice, speed, pitch=0.0, ghoul=False, spoken=None):
    """Same inputs -> same file name, so reruns skip work already done.

    Pitch, ghoul, and a spoken-line override are added only when they
    change the sound. With none of them set, the name matches older files
    hashed from voice|speed|fact alone.
    """
    key = f"{voice}|{speed}|{fact}"
    if pitch:
        key += f"|pitch={_pitch_text(pitch)}"
    if ghoul:
        key += "|ghoul"
    if spoken is not None and spoken != fact:
        key += f"|spoken={spoken}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12] + ".wav"


def write_manifest(mapping, voice_dir=VOICE_DIR):
    """voices.js: window.GNOME_VOICES = {"fact text": "voice/abc.wav", ...}"""
    js = "// Made by tools/make_gnome_voices.py. Don't edit by hand; rerun the script.\n"
    js += "window.GNOME_VOICES = " + json.dumps(mapping, indent=1, ensure_ascii=False) + ";\n"
    (voice_dir / "voices.js").write_text(js, encoding="utf-8")


def chosen_pitch(pitch, ghoul):
    """Semitones to apply. An explicit --pitch wins, including 0.

    --ghoul with no --pitch drops the voice about 4 semitones.
    """
    if pitch is None:
        return GHOUL_PITCH if ghoul else 0.0
    return float(pitch)


def _keep_under_one(samples, limit=0.99):
    """Turn the volume down only when the loudest sample would clip."""
    import numpy as np

    audio = np.asarray(samples, dtype=np.float64).reshape(-1)
    if audio.size == 0:
        return audio.astype(np.float32)
    peak = float(np.max(np.abs(audio)))
    if peak > limit:
        audio = audio * (limit / peak)
    return audio.astype(np.float32)


def _phase_vocoder(spectrum, rate, hop):
    """Stretch a spectrum. rate > 1 reads it faster (shorter audio, same pitch).

    Each slice keeps track of how the wave was moving, so the result
    doesn't buzz when the slices are put back together.
    """
    import numpy as np

    n_bins = spectrum.shape[0]
    steps = np.arange(0, spectrum.shape[1], rate, dtype=np.float64)
    if steps.size == 0:
        steps = np.zeros(1)
    stretched = np.zeros((n_bins, steps.size), dtype=np.complex128)
    # How far the phase normally moves in one hop, from low bin to high bin.
    hop_phase = np.linspace(0, np.pi * hop, n_bins)
    phase = np.angle(spectrum[:, 0])
    padded = np.pad(spectrum, [(0, 0), (0, 2)], mode="constant")
    for index, step in enumerate(steps):
        start = int(step)
        columns = padded[:, start:start + 2]
        blend = step - start
        magnitude = (1.0 - blend) * np.abs(columns[:, 0]) + blend * np.abs(columns[:, 1])
        stretched[:, index] = magnitude * np.exp(1j * phase)
        delta = np.angle(columns[:, 1]) - np.angle(columns[:, 0]) - hop_phase
        delta -= 2.0 * np.pi * np.round(delta / (2.0 * np.pi))
        phase = np.angle(np.exp(1j * (phase + hop_phase + delta)))
    return stretched


def _time_stretch(samples, rate, n_fft):
    """Change length by 1/rate without changing pitch. rate 2 = half as long."""
    import numpy as np

    audio = np.asarray(samples, dtype=np.float64).reshape(-1)
    hop = n_fft // 4
    window = np.hanning(n_fft)
    pad = n_fft // 2
    padded = np.pad(audio, (pad, pad))
    if len(padded) < n_fft:
        padded = np.pad(padded, (0, n_fft - len(padded)))
    n_frames = 1 + (len(padded) - n_fft) // hop
    spectrum = np.empty((n_fft // 2 + 1, n_frames), dtype=np.complex128)
    for i in range(n_frames):
        frame = padded[i * hop:i * hop + n_fft] * window
        spectrum[:, i] = np.fft.rfft(frame)
    stretched = _phase_vocoder(spectrum, rate, hop)
    n_out = stretched.shape[1]
    mixed = np.zeros(n_fft + hop * max(0, n_out - 1))
    weight = np.zeros_like(mixed)
    for i in range(n_out):
        frame = np.fft.irfft(stretched[:, i], n=n_fft).real * window
        start = i * hop
        mixed[start:start + n_fft] += frame
        weight[start:start + n_fft] += window ** 2
    loud_enough = weight > 1e-8
    mixed[loud_enough] /= weight[loud_enough]
    mixed = mixed[pad:] if len(mixed) > pad else mixed
    target = max(1, int(round(len(audio) / rate)))
    if len(mixed) < target:
        mixed = np.pad(mixed, (0, target - len(mixed)))
    return mixed[:target]


def shift_pitch(samples, semitones, sr=SAMPLE_RATE):
    """Raise or lower pitch by `semitones` without changing how long the line is.

    Kokoro has no pitch knob. Stretching the audio changes its length but
    not its pitch. Resampling that result back to the old length puts the
    timing back and leaves the new pitch behind.
    """
    import numpy as np
    from scipy.signal import resample

    audio = np.asarray(samples, dtype=np.float64).reshape(-1)
    if not semitones or audio.size == 0:
        return audio.astype(np.float32)
    # Smaller window for a very short clip, so the math still has room.
    n_fft = 2048
    while n_fft // 2 >= len(audio) and n_fft > 128:
        n_fft //= 2
    # +12 semitones is one octave up, which is twice the frequency.
    rate = 2.0 ** (-float(semitones) / 12.0)
    stretched = _time_stretch(audio, rate, n_fft)
    shifted = resample(stretched, len(audio))
    # Keep the line about as loud as Kokoro made it.
    before = float(np.sqrt(np.mean(audio ** 2)))
    after = float(np.sqrt(np.mean(shifted ** 2)))
    if before > 0 and after > 1e-8:
        shifted = shifted * (before / after)
    return _keep_under_one(shifted)


def add_ghoul(samples, sr=SAMPLE_RATE):
    """Light grit and a short hollow echo. Pitch is handled separately.

    Most of the original voice stays in the mix so the words stay clear.
    The repeats are darker and quieter, like a Forsaken speaking in a crypt.
    """
    import numpy as np
    from scipy.signal import butter, sosfilt

    audio = np.asarray(samples, dtype=np.float64).reshape(-1)
    if audio.size == 0:
        return audio.astype(np.float32)
    # Soft crunch, blended in lightly so it doesn't turn into a buzz.
    crunch = np.tanh(audio * 2.2)
    dry = 0.86 * audio + 0.14 * crunch
    # Darken a copy for the echoes. The dry voice itself stays bright.
    dark = sosfilt(butter(2, 1100, btype="low", fs=sr, output="sos"), dry)
    first = int(round(sr * 0.072))
    second = int(round(sr * 0.145))
    wet = np.zeros(len(dry) + second, dtype=np.float64)
    wet[first:first + len(dark)] += dark * 0.32
    wet[second:second + len(dark)] += dark * 0.16
    # A very short repeat on the echo only. That is the hollow part.
    comb = max(1, int(round(sr * 0.011)))
    wet[comb:] += wet[:-comb] * 0.28
    mixed = np.zeros(len(wet), dtype=np.float64)
    mixed[:len(dry)] += dry
    mixed += wet
    return _keep_under_one(mixed)


def shape_audio(samples, pitch=0.0, ghoul=False, sr=SAMPLE_RATE):
    """Pitch shift, then the ghoul effect, when those options are on."""
    import numpy as np

    audio = np.asarray(samples, dtype=np.float32).reshape(-1)
    if not pitch and not ghoul:
        return audio
    if pitch:
        audio = shift_pitch(audio, pitch, sr)
    if ghoul:
        audio = add_ghoul(audio, sr)
    return np.asarray(audio, dtype=np.float32).reshape(-1)


def build(facts, speak, voice, speed, voice_dir=VOICE_DIR, pitch=0.0, ghoul=False, spoken=None):
    """Make missing audio, delete stale audio, write the manifest.
    speak(text) must return a 1-D float array of audio samples.
    `spoken` maps a plain fact to the marked-up line Kokoro should say.
    voices.js is still keyed by the plain fact."""
    import soundfile as sf

    spoken = spoken or {}
    voice_dir.mkdir(parents=True, exist_ok=True)
    mapping, made = {}, 0
    for i, fact in enumerate(facts, 1):
        say = line_to_speak(fact, spoken)
        name = file_name(fact, voice, speed, pitch=pitch, ghoul=ghoul, spoken=say)
        mapping[fact] = f"voice/{name}"
        out = voice_dir / name
        if out.is_file():
            continue
        print(f"[{i}/{len(facts)}] {fact[:60]}...")
        audio = shape_audio(speak(say), pitch, ghoul)
        sf.write(out, audio, SAMPLE_RATE)
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
        # Leave the text alone, markup included. For af_ and bf_ voices,
        # KPipeline sends it to misaki's English G2P, which understands
        # [word](/phonemes/) and [word](+1), plus pauses like … — ;
        chunks = [audio for _, _, audio in pipe(text, voice=voice, speed=speed)]
        return np.concatenate([np.asarray(c) for c in chunks])

    return speak


def main():
    parser = argparse.ArgumentParser(description="Pre-record Fact Gnome lines with Kokoro.")
    parser.add_argument("--voice", default="af_bella", help="Kokoro voice, e.g. af_bella, af_nicole, af_heart, bf_emma")
    parser.add_argument("--speed", type=float, default=1.1, help="1.0 = normal")
    parser.add_argument("--pitch", type=float, default=None,
                        help="Semitones after speaking. 2 is a bit higher. Default 0, or -4 with --ghoul.")
    parser.add_argument("--ghoul", action="store_true",
                        help="Undead effect: lower pitch, a little grit, and a hollow echo.")
    args = parser.parse_args()

    facts = read_facts()
    spoken = read_spoken()
    pitch = chosen_pitch(args.pitch, args.ghoul)
    print(f"{len(facts)} facts in {FACTS_FILE}")
    notes = []
    if pitch:
        notes.append(f"pitch {pitch:g}")
    if args.ghoul:
        notes.append("ghoul")
    used = sum(1 for fact in facts if fact in spoken)
    if used:
        notes.append(f"{used} spoken lines")
    if notes:
        print("Using " + ", ".join(notes))
    skipped = [key for key in spoken if key not in facts]
    if skipped:
        print(f"Warning: {len(skipped)} spoken.js keys don't match a fact, so they were skipped.")
        print("First one:", skipped[0][:80])
    build(
        facts,
        kokoro_speaker(args.voice, args.speed),
        args.voice,
        args.speed,
        pitch=pitch,
        ghoul=args.ghoul,
        spoken=spoken,
    )


if __name__ == "__main__":
    main()
