SetTitleMatchMode, 2
DetectHiddenWindows, On

; Find Snap Camera window
WinGet, snap_hwnd, ID, Snap Camera
if snap_hwnd
{
    ; Make sure window is visible and focused
    WinRestore, ahk_id %snap_hwnd%
    WinActivate, ahk_id %snap_hwnd%
    Sleep, 200  ; give time to focus

    ; Send the key like a real user would
    Send, ^9  ; Ctrl + 9

    ; Optional: minimize again
    Sleep, 50
    WinMinimize, ahk_id %snap_hwnd%

    TrayTip, Snap Camera, Ctrl+9 filter activated!, 1
}
else
{
    TrayTip, Snap Camera, Window not found!, 2
}
