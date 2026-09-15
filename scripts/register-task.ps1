<#
.SYNOPSIS  Register/remove the weekday 09:15 "Claude Open Loops Refresh" task.
.EXAMPLE   powershell -ExecutionPolicy Bypass -File scripts\register-task.ps1 [-At 09:15] [-Remove]
#>
[CmdletBinding()]
param([string]$TaskName = "Claude Open Loops Refresh", [string]$At = "09:15", [switch]$Remove)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Runner = Join-Path $Root "scripts\run-refresh.ps1"
if ($Remove) { try { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop; "Removed $TaskName" } catch { "No task $TaskName" }; exit 0 }
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $Runner) -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At $At
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 60) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Refreshes the Open Loops tracker from Slack + Gmail via claude -p. Read-only; never sends." -Force | Out-Null
"Registered '$TaskName' weekdays at $At. Test: Start-ScheduledTask -TaskName '$TaskName'"
