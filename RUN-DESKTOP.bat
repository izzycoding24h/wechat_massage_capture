@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  call SETUP-WINDOWS.bat
  if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
)

call ".venv\Scripts\activate.bat"
python desktop_app.py
echo.
pause
