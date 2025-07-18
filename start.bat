@echo off
cd /d %~dp0

echo Starte das Lagersystem...

:: Öffnet automatisch den Browser
start http://192.168.178.93:5000

:: Startet den Python-Server
python run.py

pause
