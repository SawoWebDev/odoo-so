@echo off
rem Run ONCE. Starts the share bridge hidden (no window) every time you sign in to Windows, and starts it now.
rem It also saves your login for the label share in Windows (Credential Manager). Without that, Windows is not signed in
rem to the share after a restart and the hidden bridge can only wait, so the app says "the share helper is not running".
rem It waits for the network share by itself, so nothing has to be clicked after a restart.
rem To undo: remove-share-bridge-autostart.bat
cd /d "%~dp0"
set "PYW="
for /f "delims=" %%p in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%p"
if not defined PYW goto :nopython

rem 1. Is Windows signed in to the share? If not, ask for the login once and save it (the password is typed, never written to a file).
dir "\\DATA-SERVER\Marketing" >nul 2>&1
if not errorlevel 1 goto :signedin
echo Windows is not signed in to \\DATA-SERVER\Marketing yet.
echo Enter the login you use to open that folder in Explorer. It is saved in Windows, so this is asked only once.
set "SHAREUSER="
set /p "SHAREUSER=User name (e.g. firstname.lastname, or DOMAIN\firstname.lastname): "
if not defined SHAREUSER goto :signedin
echo Type the password twice (once for the server name, once for its address).
cmdkey /add:DATA-SERVER /user:"%SHAREUSER%" /pass
cmdkey /add:172.16.0.4 /user:"%SHAREUSER%" /pass
dir "\\DATA-SERVER\Marketing" >nul 2>&1
if errorlevel 1 (
  echo.
  echo WARNING: Windows still cannot open \\DATA-SERVER\Marketing with that login. Check the user name and password,
  echo and run this file again. The bridge is set up anyway and will connect by itself once the login works.
)
:signedin

rem 2. Stop a bridge that is already running (for example one stuck waiting for the share), so only one is left.
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*share_bridge.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"

rem 3. Start the bridge hidden at every sign-in, and now.
set "VBS=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\sawo-share-bridge.vbs"
> "%VBS%" echo CreateObject("WScript.Shell").Run """%PYW%"" ""%~dp0backend\scripts\share_bridge.py"" --root ""\\DATA-SERVER\Marketing"" --wait", 0, False
wscript "%VBS%"
echo The share bridge now starts by itself at every sign-in, and it is running now (hidden).
echo Startup entry: %VBS%
pause
exit /b 0

:nopython
echo pythonw.exe was not found. Install Python from python.org, then run this again.
pause
exit /b 1
