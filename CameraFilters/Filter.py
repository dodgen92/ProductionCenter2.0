import random
import subprocess
import time
from pathlib import Path

AHK_EXE = r"C:\Program Files\AutoHotkey\v1.1.37.02\AutoHotkeyU64.exe"

HERE = Path(__file__).resolve().parent

FILTERS = [
    str(HERE / "nugget.ahk"),
    str(HERE / "pixar.ahk"),
    str(HERE / "Trueform.ahk"),
    str(HERE / "filter_ctrl0.ahk"),
    str(HERE / "filter_ctrl9.ahk"),
    str(HERE / "filter_ctrlp.ahk"),
    str(HERE / "filter_ctrll.ahk"),
    str(HERE / "filter_ctrlk.ahk"),
    str(HERE / "filter_ctrlsemicolon.ahk"),
]


def main():
    filter_script = random.choice(FILTERS)

    print(f"🎲 Random filter selected: {filter_script}")

    time.sleep(2)

    cmd = f'"{AHK_EXE}" "{filter_script}"'

    subprocess.run(cmd, shell=True)


if __name__ == "__main__":
    main()
