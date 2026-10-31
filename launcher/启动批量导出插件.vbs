' Portable launcher for NX Batch PDF Exporter
' Locates its own folder, so the package also works after being copied/moved.
Option Explicit

Dim fso, shell, root, pythonw, script
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
root = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = root & "\python\pythonw.exe"
script = root & "\standalone.py"

If Not fso.FileExists(pythonw) Then
    If fso.FileExists(root & "\python\python.exe") Then
        pythonw = root & "\python\python.exe"
    End If
End If

If Not fso.FileExists(pythonw) Or Not fso.FileExists(script) Then
    MsgBox "The portable package is incomplete (python runtime or standalone.py missing)." & vbCrLf & _
           "Please extract the whole zip file again.", 16, "NX Batch PDF Exporter"
    WScript.Quit 1
End If

shell.CurrentDirectory = root
shell.Run """" & pythonw & """ """ & script & """", 1, False
