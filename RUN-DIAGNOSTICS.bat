@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  call SETUP-WINDOWS.bat
  if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
)

echo.
echo This runs one-shot diagnostics only. It will not scroll the chat.
echo Keep the target WeChat group visible and in front before continuing.
echo.
set /p GROUP_NAME=Group name or identifying text: 
set /p START_DATE=Start date YYYY-MM-DD: 
set /p END_DATE=End date YYYY-MM-DD [default today]: 
set /p OUTPUT_DIR=Output directory [blank = auto]: 

set "END_ARG="
if not "%END_DATE%"=="" set END_ARG=--end-date "%END_DATE%"

set "OUT_ARG="
if not "%OUTPUT_DIR%"=="" set OUT_ARG=--output-dir "%OUTPUT_DIR%"

call ".venv\Scripts\activate.bat"
python capture_wechat_group.py --group-name "%GROUP_NAME%" --start-date "%START_DATE%" %END_ARG% %OUT_ARG% --diagnose-capture
echo.
pause
