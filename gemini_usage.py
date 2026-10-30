"""Daily Gemini call counts shared by the monk and Benito.

The JSON file stores counts only. It never stores the API key.
A new local day starts the counts over, including after a restart.
"""

import json
import os
import threading
from datetime import date
from pathlib import Path

USAGE_FILE = Path(__file__).resolve().parent / "gemini_usage.json"
_lock = threading.Lock()


def _read():
    try:
        loaded = json.loads(Path(USAGE_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    return loaded


def _write(data):
    path = Path(USAGE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data), encoding="utf-8")
    os.replace(temporary, path)


def gemini_usage(feature, bump=False):
    """Return (this feature's count today, total calls today).

    bump=True adds one call for `feature` first. `feature` is a short name
    such as "monk" or "benito", never "day".
    """

    with _lock:
        today = date.today().isoformat()
        data = _read()
        if data.get("day") != today:
            data = {"day": today}
        if bump:
            try:
                current = int(data.get(feature) or 0)
            except (TypeError, ValueError):
                current = 0
            data[feature] = current + 1
            _write(data)

        feature_count = 0
        total = 0
        for key, value in data.items():
            if key == "day":
                continue
            try:
                count = int(value)
            except (TypeError, ValueError):
                continue
            total += count
            if key == feature:
                feature_count = count
        return feature_count, total
