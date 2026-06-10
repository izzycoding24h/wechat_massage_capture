$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
  py -3.10 -m venv .venv
}

& ".venv\Scripts\python.exe" -m pip install --upgrade pip
& ".venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".venv\Scripts\python.exe" -m pip install pyinstaller

if (Test-Path "dist\WechatMessageCapture") {
  Remove-Item "dist\WechatMessageCapture" -Recurse -Force
}

& ".venv\Scripts\python.exe" -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --onedir `
  --name WechatMessageCapture `
  --add-data "README.md;." `
  --add-data "LICENSE;." `
  desktop_app.py

Write-Host ""
Write-Host "Built dist\WechatMessageCapture\WechatMessageCapture.exe"
Write-Host "To create the installer, open installer\WechatMessageCapture.iss with Inno Setup and compile it."
