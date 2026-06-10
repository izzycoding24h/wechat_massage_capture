@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  call SETUP-WINDOWS.bat
  if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
)

echo.
echo This tests whether the target WeChat chat area actually scrolls.
echo It saves scroll-test\before.png and scroll-test\after.png, then exits.
echo Keep the target WeChat group visible and in front before continuing.
echo.
set /p GROUP_NAME=Group name or identifying text: 
set /p START_DATE=Start date YYYY-MM-DD: 
set /p END_DATE=End date YYYY-MM-DD [default today]: 
set /p OUTPUT_DIR=Output directory [blank = auto]: 
set /p SCROLL_MODE=Scroll mode [blank = adaptive, options adaptive/wheel/pageup/drag]: 
set /p SCROLL_CLICKS=Wheel clicks [blank = 30, ignored by adaptive]: 
set /p SCROLL_BURSTS=Scroll bursts [blank = 3, ignored by adaptive]: 
set /p PAGEUP_PRESSES=PageUp presses [blank = 1, only for pageup mode]: 
set /p TARGET_OVERLAP=Target overlap [blank = 0.35, only for adaptive]: 
set /p ADAPTIVE_STEP=Adaptive step wheel clicks [blank = 15]: 
set /p ADAPTIVE_FIXED=Adaptive fixed steps [blank = adaptive measure, use 8 to test fixed fast-scroll]: 

set "END_ARG="
if not "%END_DATE%"=="" set END_ARG=--end-date "%END_DATE%"

set "OUT_ARG="
if not "%OUTPUT_DIR%"=="" set OUT_ARG=--output-dir "%OUTPUT_DIR%"

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

call ".venv\Scripts\activate.bat"
python capture_wechat_group.py --group-name "%GROUP_NAME%" --start-date "%START_DATE%" %END_ARG% %OUT_ARG% %MODE_ARG% %SCROLL_ARG% %BURSTS_ARG% %PAGEUP_ARG% %TARGET_ARG% %ADAPTIVE_ARG% %FIXED_ARG% --scroll-test
echo.
pause
