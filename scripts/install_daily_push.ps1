# Register the Windows scheduled task "FileGo-DailyPush".
#
# The task runs scripts\auto_push.ps1 every day at 00:00 (local time). If the
# computer was asleep or off at that moment, Windows starts the task as soon as
# possible afterwards (StartWhenAvailable). The task runs in the current user's
# session so that the cached GitHub credentials of Git Credential Manager work.
#
# Run this script once; re-run it after moving the repository or changing the
# schedule. Remove the task with:
#   schtasks /delete /tn FileGo-DailyPush /f
#
# Keep this file ASCII-only: Windows PowerShell 5.1 reads scripts as ANSI.

$ErrorActionPreference = "Stop"

$repoRoot   = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $repoRoot "scripts\auto_push.ps1"
$taskName   = "FileGo-DailyPush"
$userId     = "$env:USERDOMAIN\$env:USERNAME"

if (-not (Test-Path $scriptPath)) {
    throw "auto_push.ps1 not found: $scriptPath"
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $scriptPath)
$trigger = New-ScheduledTaskTrigger -Daily -At "00:00"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force `
    -Description "Commit and push FileGo changes to GitHub every day at 00:00." | Out-Null

Write-Host "Registered scheduled task '$taskName'"
Write-Host "  action : powershell.exe -File `"$scriptPath`""
Write-Host "  trigger: daily at 00:00 (missed runs start when the computer is back)"
Write-Host "  log    : $env:LOCALAPPDATA\FileGo\auto_push.log"