' start_hidden.vbs
' Runs face_lock.py without a console window.

Set WshShell = CreateObject("WScript.Shell")
projectDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\") - 1)
pythonExe = projectDir & "\venv\Scripts\pythonw.exe"
scriptFile = projectDir & "\face_lock.py"
installerFile = projectDir & "\install_unlock_task.ps1"
powershellExe = "powershell.exe"

WshShell.CurrentDirectory = projectDir
WshShell.Run """" & powershellExe & """ -NoProfile -ExecutionPolicy Bypass -File """ & installerFile & """", 0, True
WshShell.Run """" & pythonExe & """ """ & scriptFile & """", 0, False
