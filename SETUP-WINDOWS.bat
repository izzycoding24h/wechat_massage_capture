@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  set "PY_CMD=py -3"
) else (
  set "PY_CMD=python"
)

echo Creating Python virtual environment...
%PY_CMD% -m venv .venv
if %ERRORLEVEL% NEQ 0 (
  echo Failed to create virtual environment. Install Python 3.10+ and try again.
  pause
  exit /b 1
)

call ".venv\Scripts\activate.bat"
if "%PIP_INDEX_URL%"=="" set "PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple"
echo Using pip index: %PIP_INDEX_URL%
python -m pip install -i "%PIP_INDEX_URL%" --upgrade pip
python -m pip install -i "%PIP_INDEX_URL%" -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
  echo Dependency installation failed.
  pause
  exit /b 1
)

echo.
echo Setup complete.
pause
