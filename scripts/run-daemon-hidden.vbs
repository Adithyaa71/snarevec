' SnareVec daemon launcher — runs with no visible console window.
' Path is resolved relative to this script's own location, so it still
' works if the repo folder gets moved or renamed.

Set fso = CreateObject("Scripting.FileSystemObject")
scriptsDir = fso.GetParentFolderName(WScript.ScriptFullName)
repoDir = fso.GetParentFolderName(scriptsDir)
daemonDir = fso.BuildPath(repoDir, "daemon")

Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = daemonDir
WshShell.Run "python main.py", 0, False
