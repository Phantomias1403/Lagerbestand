@echo off
cd /d %~dp0

echo Starte das Lagersystem...

:: Öffnet automatisch den Browser
start http://127.0.0.1:5000

:: Startet den Python-Server
python run.py

pause
