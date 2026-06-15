@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo === Checking PyInstaller ===
pip show pyinstaller >nul 2>&1 || pip install pyinstaller

echo.
echo === Building EXE ===
pyinstaller myterm.spec

echo.
echo === Done ===
echo EXE: dist\MyTerm.exe
pause
