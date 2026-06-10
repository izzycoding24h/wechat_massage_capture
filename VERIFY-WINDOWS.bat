@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  call SETUP-WINDOWS.bat
  if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
)

set /p EVIDENCE_DIR=Evidence directory to verify [blank = current folder]: 
if "%EVIDENCE_DIR%"=="" set "EVIDENCE_DIR=."

call ".venv\Scripts\activate.bat"
python verify_hashes.py "%EVIDENCE_DIR%"
echo.
pause
