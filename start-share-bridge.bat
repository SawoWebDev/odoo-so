@echo off
rem Lets the Docker app read the label share with YOUR Windows access (no password needed). Keep this window open.
cd /d "%~dp0"
python backend\scripts\share_bridge.py --root "\\172.16.0.4\Marketing"
pause
