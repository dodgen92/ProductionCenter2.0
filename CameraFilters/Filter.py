import random
import subprocess
import time

AHK_EXE = r"C:\Program Files\AutoHotkey\v1.1.37.02\AutoHotkeyU64.exe"

FILTERS = [
    r"C:\Users\tyler\Desktop\ProductionCenter2.0\CameraFilters\nugget.ahk",
    r"C:\Users\tyler\Desktop\ProductionCenter2.0\CameraFilters\pixar.ahk",
    r"C:\Users\tyler\Desktop\ProductionCenter2.0\CameraFilters\Trueform.ahk",
    ]

filter_script = random.choice(FILTERS)

print(f"🎲 Random filter selected: {filter_script}")

time.sleep(2)

cmd = f'"{AHK_EXE}" "{filter_script}"'

subprocess.run(cmd, shell=True)