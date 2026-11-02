SetTitleMatchMode, 2  
DetectHiddenWindows, On

; 
    if WinExist("Snap Camera") {
        ; Activate the Snap Camera window (no need to bring it to the front)
        WinActivate  ; Ensure Snap Camera gets the input
        WinMinimize  ; Minimize the Snap Camera window so it stays in the background
        Sleep, 100  
        ; Send Ctrl + = to switch to the de filter
        Send, ^=
        TrayTip, Snap Camera, Filter Deactivated!, 1
    }
        
return
