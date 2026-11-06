"""pytest loads this file before any test module.

You do not run it yourself. It puts the project folder on the import path and
sets dummy env vars so `import Server` does not need a real .env or OBS.
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import lull

# These values are fake. They exist so the tests are deterministic.
os.environ.setdefault("OBS_PORT", "4455")
os.environ.setdefault("OBS_HOST", "127.0.0.1")
os.environ.setdefault("OBS_PASSWORD", "test-only")
os.environ.setdefault("TWITCH_CLIENT_ID", "test-client-id")
os.environ.setdefault("BROADCASTER_USER_ID", "12345")


@pytest.fixture(autouse=True)
def reset_lull_state():
    """Drop Lull Helper's RAM buffers so tests do not share speech or chat."""

    lull.reset_state()
    yield
    lull.reset_state()
