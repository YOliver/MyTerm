@echo off
setlocal EnableDelayedExpansion

REM ========================================================================
REM 一键发布脚本：跑 PyInstaller 出 exe，再用 Inno Setup 打安装包。
REM
REM 用法（在工程根目录下双击或命令行执行）：
REM     scripts\release.bat
REM
REM 产物：
REM     dist\MyTerm.exe                    （PyInstaller 单文件）
REM     dist\MyTerm-Setup-<version>.exe    （Inno Setup 安装包）
REM ========================================================================

cd /d "%~dp0\.."

REM ---- 1. 读版本号 -------------------------------------------------------
for /f "usebackq tokens=*" %%v in (`python -c "from version import __version__; print(__version__)"`) do set "APP_VERSION=%%v"
if "%APP_VERSION%"=="" (
    echo [ERROR] 读不到 version.py 里的 __version__
    exit /b 1
)
echo [release] 版本号: %APP_VERSION%

REM ---- 2. 重新生成 icon.ico（icon.png 改了也能跟上） ---------------------
echo [release] 生成 icon.ico...
python scripts\make_icon.py
if errorlevel 1 (
    echo [ERROR] 生成 icon.ico 失败
    exit /b 1
)

REM ---- 3. PyInstaller 出 exe --------------------------------------------
echo [release] 清理 build/ dist/ ...
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

echo [release] 跑 PyInstaller...
python -m PyInstaller myterm.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller 失败
    exit /b 1
)
if not exist "dist\MyTerm.exe" (
    echo [ERROR] dist\MyTerm.exe 没生成
    exit /b 1
)

REM ---- 4. 找 Inno Setup --------------------------------------------------
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe"      set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if "%ISCC%"=="" (
    echo [ERROR] 找不到 Inno Setup 6 ISCC.exe
    echo         请到 https://jrsoftware.org/isinfo.php 下载安装，或手动设置 ISCC 路径。
    exit /b 1
)
echo [release] 使用 Inno Setup: %ISCC%

REM ---- 5. 跑 Inno Setup --------------------------------------------------
echo [release] 编译安装包...
"%ISCC%" /DAppVersion=%APP_VERSION% installer\myterm.iss
if errorlevel 1 (
    echo [ERROR] Inno Setup 编译失败
    exit /b 1
)

echo.
echo [release] 完成！产物：
dir /b dist\MyTerm-Setup-*.exe
echo.
endlocal
