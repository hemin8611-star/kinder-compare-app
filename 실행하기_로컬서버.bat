@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo [유치원콕] 로컬 웹서버(http://localhost:8080)를 시작합니다...
start "" "http://localhost:8080"
python -m http.server 8080
