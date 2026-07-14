' Installs (or updates) a "SnareVec Daemon" shortcut in the current user's
' Startup folder, pointing at run-daemon-hidden.vbs in this same folder.
' Double-click this file once to enable auto-start on login.
'
' If an old "ClawCapture Daemon" shortcut exists in Startup, delete it
' manually (right-click > Delete) — this script only adds the new one,
' it doesn't remove the old one for you.

Set fso = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")

scriptsDir = fso.GetParentFolderName(WScript.ScriptFullName)
hiddenVbs = fso.BuildPath(scriptsDir, "run-daemon-hidden.vbs")

startupDir = WshShell.SpecialFolders("Startup")
shortcutPath = fso.BuildPath(startupDir, "SnareVec Daemon.lnk")

Set shortcut = WshShell.CreateShortcut(shortcutPath)
shortcut.TargetPath = "wscript.exe"
shortcut.Arguments = """" & hiddenVbs & """"
shortcut.WorkingDirectory = scriptsDir
shortcut.Description = "SnareVec companion daemon (hidden, auto-start)"
shortcut.Save

MsgBox "SnareVec Daemon shortcut installed in:" & vbCrLf & startupDir & vbCrLf & vbCrLf & "It will auto-start next time you log in. If an old 'ClawCapture Daemon' shortcut is still there, delete it manually.", vbInformation, "SnareVec"
