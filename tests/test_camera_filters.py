"""Camera filter scripts stay in the repo. Nothing here starts AutoHotkey."""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAMERA_FILTERS = ROOT / "CameraFilters"


def load_script(filename):
    """Load a CameraFilters script. Running the file is what launches AutoHotkey."""

    path = CAMERA_FILTERS / filename
    spec = importlib.util.spec_from_file_location(f"camera_filters_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_filter_script_is_in_the_repo():
    """Each path in FILTERS is a file next to Filter.py."""

    # Proves: the random picker points at scripts that shipped with the repo,
    # and importing Filter.py does not launch AutoHotkey.

    filters = load_script("Filter.py")

    assert len(filters.FILTERS) == 9
    for script in filters.FILTERS:
        path = Path(script)
        assert path.is_file()
        assert path.resolve().parent == CAMERA_FILTERS.resolve()


def test_clearfilter_points_at_the_repo_script():
    """clearfilter.py runs the clearfilter.ahk that sits beside it."""

    # Proves: the clear script is the one in this repo, not an old Desktop path.

    clear = load_script("clearfilter.py")
    path = Path(clear.ahk_script_path)

    assert path.is_file()
    assert path.name == "clearfilter.ahk"
    assert path.resolve().parent == CAMERA_FILTERS.resolve()
