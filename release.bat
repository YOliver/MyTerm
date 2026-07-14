@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo === Checking PyInstaller ===
pip show pyinstaller >nul 2>&1 || pip install pyinstaller

echo.
echo === Building EXE ===
pyinstaller myterm.spec

echo.
echo === Building Installer ===

for /f "tokens=2 delims==" %%a in ('findstr /b "__version__" version.py') do set VER=%%a
set VER=%VER: =%
set VER=%VER:"=%

"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" /dAppVersion=%VER% installer\myterm.iss

echo.
echo === Done ===
echo EXE: dist\MyTerm.exe
echo Installer: dist\MyTerm-Setup-%VER%.exe
pause
