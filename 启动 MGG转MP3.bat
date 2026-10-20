@echo off
chcp 65001 >nul 2>&1
setlocal
cd /d "%~dp0"

set "PYW=%~dp0.venv\Scripts\pythonw.exe"
if exist "%PYW%" goto run

set "PYW="
for %%i in (pythonw.exe) do if not "%%~$PATH:i"=="" set "PYW=%%~$PATH:i"
if not defined PYW goto nopython

:run
start "" "%PYW%" "%~dp0app.py"
exit /b 0

:nopython
echo [错误] 没有找到 Python。
echo.
echo 请先安装 Python 3.10+，然后在项目目录执行：
echo     python -m venv .venv
echo     .venv\Scripts\pip install -r requirements.txt
echo.
pause
exit /b 1
