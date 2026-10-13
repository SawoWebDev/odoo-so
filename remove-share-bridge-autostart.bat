@echo off
rem Undoes install-share-bridge-autostart.bat: no more automatic start at sign-in, and stops the running hidden bridge.
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\sawo-share-bridge.vbs" 2>nul
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object { $_.CommandLine -like '*share_bridge.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo The share bridge no longer starts automatically. Use start-share-bridge.bat to run it by hand.
pause
