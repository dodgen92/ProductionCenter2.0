import subprocess
import time


# First, we attempt to trigger UAC elevation automatically
# This will automatically prompt for admin permission without requiring a password

#if not pyuac.isUserAdmin():
#    pyuac.runAsAdmin()

# Path to AutoHotkey.exe
ahk_exe_path = r"C:\Program Files\AutoHotkey\v1.1.37.02\AutoHotkeyU64.exe"  

# Path to your AHK script
ahk_script_path = r"C:\Users\tyler\Desktop\ProductionCenter\clearfilter.ahk"

# Command to run the AHK script with admin privileges using 'runas'
cmd = f'"{ahk_exe_path}" "{ahk_script_path}"'

time.sleep(2)

# Run the command (ensure admin privileges)
subprocess.run(cmd, shell=True)