<#
  Open Loops - one-click installer for Windows.
  Right-click this file -> "Run with PowerShell". Or from a terminal:
      powershell -ExecutionPolicy Bypass -File setup.ps1

  What it does (all on this computer, nothing sent anywhere):
    1. Installs Python and Claude Code if they're missing (using Windows' own installer, winget).
    2. Copies Open Loops to your user folder.
    3. Puts an "Open Loops" icon on your Desktop.
    4. Sets it to refresh every weekday morning (default 09:15).
    5. Opens the app - which walks you through connecting Slack and email.
#>
[CmdletBinding()]
param([string]$At = "09:15", [string]$Name = "")

$ErrorActionPreference = "Stop"
function Say($t) { Write-Host ""; Write-Host "  $t" -ForegroundColor Cyan }
function Ok($t)  { Write-Host "  [ok] $t" -ForegroundColor Green }

Write-Host ""
Write-Host "  ============================" -ForegroundColor Cyan
Write-Host "   Open Loops - setup"        -ForegroundColor Cyan
Write-Host "  ============================" -ForegroundColor Cyan

# ---------- 1. Python ----------
Say "Checking Python..."
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Say "Installing Python (this can take a minute)..."
    winget install --id Python.Python.3.13 -e --accept-source-agreements --accept-package-agreements --silent | Out-Null
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}
Ok ("Python " + ((python --version) -replace "Python ",""))

# ---------- 2. Claude Code ----------
Say "Checking Claude..."
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Say "Installing Claude Code (this can take a minute)..."
    try {
        Invoke-RestMethod https://claude.ai/install.ps1 | Invoke-Expression
    } catch {
        winget install --id Anthropic.ClaudeCode -e --accept-source-agreements --accept-package-agreements --silent | Out-Null
    }
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}
if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Host "  Couldn't install Claude automatically. Please install it from https://claude.ai/code and run this again." -ForegroundColor Yellow
    exit 1
}
Ok "Claude is installed"

# ---------- 3. Copy files ----------
$Src  = $PSScriptRoot
# Install into the user's local app-data folder - no admin rights needed, and it works wherever the
# download was unzipped (Downloads, Desktop, a USB stick). The Desktop icon points here, so the
# downloaded folder can be deleted afterwards.
$Dest = Join-Path $env:LOCALAPPDATA "OpenLoops"
if ((Resolve-Path $Src).Path -eq $Dest) { Say "Already installed here - updating." }
Say "Installing Open Loops to $Dest ..."
New-Item -ItemType Directory -Force $Dest | Out-Null
if ((Resolve-Path $Src).Path -ne $Dest) {
    Get-ChildItem $Src -Exclude "state","voice.json","state.json","config.json","people_suggested.json",".git","docs","tests",".worktrees" | Copy-Item -Destination $Dest -Recurse -Force
}
New-Item -ItemType Directory -Force (Join-Path $Dest "state\logs") | Out-Null

# fresh state + config unless the person already has them
$StateFile = Join-Path $Dest "state.json"
if (-not (Test-Path $StateFile)) {
    $cursor = (Get-Date).AddDays(-7).ToString("yyyy-MM-ddTHH:mm:sszzz")
    @{ cursor = $cursor; last_refresh = $null; loops = @() } | ConvertTo-Json | ForEach-Object { [IO.File]::WriteAllText($StateFile, $_, (New-Object Text.UTF8Encoding $false)) }  # no BOM - Python json refuses it
}
$CfgFile = Join-Path $Dest "config.json"
if (-not (Test-Path $CfgFile)) {
    while (-not $Name) { $Name = (Read-Host "  Your first name (used so messages sound like you)").Trim() }
    $tpl = Get-Content (Join-Path $Src "config.template.json") -Raw | ConvertFrom-Json
    $tpl.owner_name   = $Name
    $tpl.refresh_time = $At
    $tpl | ConvertTo-Json -Depth 6 | ForEach-Object { [IO.File]::WriteAllText($CfgFile, $_, (New-Object Text.UTF8Encoding $false)) }
}
Ok "Files in place"

# ---------- 4. Desktop icon ----------
$desk = [Environment]::GetFolderPath("Desktop")
$pyw  = (Get-Command pythonw -ErrorAction SilentlyContinue).Source
if (-not $pyw) { $pyw = (Get-Command python).Source }
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut((Join-Path $desk "Open Loops.lnk"))
$s.TargetPath = $pyw; $s.Arguments = "-m openloops.app"; $s.WorkingDirectory = $Dest
$s.IconLocation = "%SystemRoot%\System32\shell32.dll,44"; $s.Description = "Open Loops - who owes you a reply"; $s.Save()
Ok "Desktop icon created"

# ---------- 5. Morning refresh ----------
powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Dest "scripts\register-task.ps1") -At $At | Out-Null
Ok "Will refresh itself weekdays at $At"

# ---------- 6. Open it ----------
Say "Opening Open Loops - it will guide you through connecting Slack and email."
Start-Process -FilePath $pyw -ArgumentList "-m openloops.app" -WorkingDirectory $Dest
Write-Host ""
Write-Host "  Done. You can close this window." -ForegroundColor Green
Write-Host ""
