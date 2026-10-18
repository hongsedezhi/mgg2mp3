@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem 先用项目内的虚拟环境，没有就找系统 PATH 里的 pythonw
set "PYW="
if exist "%~dp0.venv\Scripts\pythonw.exe" set "PYW=%~dp0.venv\Scripts\pythonw.exe"
if not defined PYW for %%i in (pythonw.exe) do if not "%%~$PATH:i"=="" set "PYW=%%~$PATH:i"

if not defined PYW (
    echo [错误] 没有找到 Python。
    echo.
    echo 请先安装 Python 3.10+，然后在项目目录执行：
    echo     python -m venv .venv
    echo     .venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

start "" "%PYW%" "%~dp0app.py"
exit /b 0
