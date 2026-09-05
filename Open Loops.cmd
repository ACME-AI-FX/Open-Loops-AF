@echo off
rem Open Loops - double-click me.
rem   Not installed yet?  -> runs the installer (setup.ps1), which puts Open Loops in %LOCALAPPDATA%\OpenLoops
rem                          and an icon on your Desktop.
rem   Already installed?  -> starts it (hidden, no console window) and opens the page in your browser.
setlocal
set "APP=%LOCALAPPDATA%\OpenLoops\app.py"
if exist "%APP%" (
    cd /d "%LOCALAPPDATA%\OpenLoops"
    start "" pythonw app.py
    exit /b 0
)
echo Installing Open Loops...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
if errorlevel 1 pause
