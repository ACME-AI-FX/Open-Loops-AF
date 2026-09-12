<#
.SYNOPSIS  Unattended refresh of open loops (Task Scheduler, weekdays 08:40).
#>
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$LogDir = Join-Path $Root "state\logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Force $LogDir | Out-Null }
$Log = Join-Path $LogDir ("runner-" + (Get-Date -Format "yyyy-MM-dd") + ".log")
$dow = (Get-Date).DayOfWeek
if ($dow -eq "Saturday" -or $dow -eq "Sunday") { Add-Content $Log "weekend - skipped"; exit 0 }
Add-Content $Log ("=== refresh " + (Get-Date -Format "HH:mm:ss"))
$out = & python -m openloops.refresh 2>&1 | ForEach-Object { "$_" }
$out | ForEach-Object { Add-Content $Log $_ -Encoding UTF8 }
Add-Content $Log ("refresh exit " + $LASTEXITCODE)

# --- timer-driven chasing (no-op unless auto_chase.enabled in config.json) ---
Add-Content $Log ("=== autochase " + (Get-Date -Format "HH:mm:ss"))
$ac = & python -m openloops.autochase 2>&1 | ForEach-Object { "$_" }
$ac | ForEach-Object { Add-Content $Log $_ -Encoding UTF8 }
exit 0
