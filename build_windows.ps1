param(
  [string]$PipIndexUrl = $env:PIP_INDEX_URL,
  [switch]$NoMirror
)

$ErrorActionPreference = "Stop"

Set-Location -Path $PSScriptRoot

if (-not $PipIndexUrl) {
  $PipIndexUrl = "https://pypi.tuna.tsinghua.edu.cn/simple"
}

$PipArgs = @()
if (-not $NoMirror) {
  $PipHost = ([System.Uri]$PipIndexUrl).Host
  $PipArgs = @("-i", $PipIndexUrl, "--trusted-host", $PipHost)
  Write-Host "Using pip index: $PipIndexUrl"
} else {
  Write-Host "Using default pip index."
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
  py -3.10 -m venv .venv
}

& ".venv\Scripts\python.exe" -m pip install @PipArgs --upgrade pip
& ".venv\Scripts\python.exe" -m pip install @PipArgs -r requirements.txt
& ".venv\Scripts\python.exe" -m pip install @PipArgs pyinstaller

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
