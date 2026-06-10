@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  call SETUP-WINDOWS.bat
  if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
)

echo.
echo Open WeChat, open the target group chat, and put the chat at the newest/end position first.
echo During capture, press Ctrl+Alt+S when the visible messages reach the oldest/start date.
echo.

set /p GROUP_NAME=Group name or identifying text: 
set /p START_DATE=Start date YYYY-MM-DD: 
set /p END_DATE=End date YYYY-MM-DD [default today]: 
set /p OUTPUT_DIR=Output directory [blank = auto]: 
set /p MAX_SHOTS=Max screenshots [blank/0 = unlimited]: 
set /p SCROLL_MODE=Scroll mode [blank = adaptive, options adaptive/wheel/pageup/drag]: 
set /p SCROLL_CLICKS=Wheel clicks [blank = 30, ignored by adaptive]: 
set /p SCROLL_BURSTS=Scroll bursts [blank = 3, ignored by adaptive]: 
set /p PAGEUP_PRESSES=PageUp presses [blank = 1, only for pageup mode]: 
set /p TARGET_OVERLAP=Target overlap [blank = 0.35, only for adaptive]: 
set /p ADAPTIVE_STEP=Adaptive step wheel clicks [blank = 15]: 
set /p ADAPTIVE_FIXED=Adaptive fixed steps [blank = measure each screenshot, use 8 after a good scroll-test]: 
set /p LOCK_AFTER_FIRST=Lock after first adaptive calibration? [blank = no, y = yes]: 
set /p INTERVAL=Seconds between screenshots [blank = 1.2, use 0.2 for fast]: 

set "END_ARG="
if not "%END_DATE%"=="" set END_ARG=--end-date "%END_DATE%"

set "OUT_ARG="
if not "%OUTPUT_DIR%"=="" set OUT_ARG=--output-dir "%OUTPUT_DIR%"

set "MAX_ARG="
if not "%MAX_SHOTS%"=="" set "MAX_ARG=--max-screenshots %MAX_SHOTS%"

set "MODE_ARG="
if not "%SCROLL_MODE%"=="" set MODE_ARG=--scroll-mode %SCROLL_MODE%

set "SCROLL_ARG="
if not "%SCROLL_CLICKS%"=="" set SCROLL_ARG=--scroll-clicks %SCROLL_CLICKS%

set "BURSTS_ARG="
if not "%SCROLL_BURSTS%"=="" set BURSTS_ARG=--scroll-bursts %SCROLL_BURSTS%

set "PAGEUP_ARG="
if not "%PAGEUP_PRESSES%"=="" set PAGEUP_ARG=--pageup-presses %PAGEUP_PRESSES%

set "TARGET_ARG="
if not "%TARGET_OVERLAP%"=="" set TARGET_ARG=--target-overlap %TARGET_OVERLAP%

set "ADAPTIVE_ARG="
if not "%ADAPTIVE_STEP%"=="" set ADAPTIVE_ARG=--adaptive-step-clicks %ADAPTIVE_STEP%

set "FIXED_ARG="
if not "%ADAPTIVE_FIXED%"=="" set FIXED_ARG=--adaptive-fixed-steps %ADAPTIVE_FIXED%

set "LOCK_ARG="
if /I "%LOCK_AFTER_FIRST%"=="y" set LOCK_ARG=--adaptive-lock-after-first

set "INTERVAL_ARG="
if not "%INTERVAL%"=="" set INTERVAL_ARG=--interval %INTERVAL%

call ".venv\Scripts\activate.bat"
python capture_wechat_group.py --group-name "%GROUP_NAME%" --start-date "%START_DATE%" %END_ARG% %OUT_ARG% %MAX_ARG% %MODE_ARG% %SCROLL_ARG% %BURSTS_ARG% %PAGEUP_ARG% %TARGET_ARG% %ADAPTIVE_ARG% %FIXED_ARG% %LOCK_ARG% %INTERVAL_ARG%
echo.
pause
