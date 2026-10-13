@echo off
rem Run ONCE. Starts the share bridge hidden (no window) every time you sign in to Windows, and starts it now.
rem It waits for the network share by itself, so nothing has to be clicked after a restart.
rem To undo: remove-share-bridge-autostart.bat
cd /d "%~dp0"
set "PYW="
for /f "delims=" %%p in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%p"
if not defined PYW (
  echo pythonw.exe was not found. Install Python from python.org, then run this again.
  pause
  exit /b 1
)
set "VBS=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\sawo-share-bridge.vbs"
> "%VBS%" echo CreateObject("WScript.Shell").Run """%PYW%"" ""%~dp0backend\scripts\share_bridge.py"" --root ""\\DATA-SERVER\Marketing"" --wait", 0, False
wscript "%VBS%"
echo The share bridge now starts by itself at every sign-in, and it is running now (hidden).
echo Startup entry: %VBS%
pause
