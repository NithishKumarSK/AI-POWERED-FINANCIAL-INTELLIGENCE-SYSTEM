<#
register_retraining_task.ps1 -- registers scheduled_retraining.py as a
weekly Windows Task Scheduler job (item #5: "a proper, scheduled retraining
pipeline"). Not run automatically by any code in this repo -- the user (or
Ajay) runs this once, manually, to actually create the recurring task,
since registering a persistent OS-level scheduled task is a real system
change outside the project folder and deserves a deliberate, visible step
rather than happening silently as a side effect of some other script.

Usage (from an ordinary PowerShell prompt, no admin rights needed for a
per-user task):
    powershell -ExecutionPolicy Bypass -File scripts\register_retraining_task.ps1

Default schedule: every Sunday at 03:00 local time (market closed, low
contention with any interactive use of the machine). Edit $TriggerDay /
$TriggerTime below to change it.

To remove the task later:
    schtasks /delete /tn "StockPredictionAgent_WeeklyRetrain" /f
#>

$TaskName    = "StockPredictionAgent_WeeklyRetrain"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe   = "C:\Users\nithi\AppData\Local\Programs\Python\Python312\python.exe"
$ScriptPath  = Join-Path $ProjectRoot "scripts\scheduled_retraining.py"
$TriggerDay  = "SUN"
$TriggerTime = "03:00"

if (-not (Test-Path $PythonExe)) {
    Write-Error "Python interpreter not found at $PythonExe -- edit `$PythonExe in this script to match your environment, then re-run."
    exit 1
}
if (-not (Test-Path $ScriptPath)) {
    Write-Error "scheduled_retraining.py not found at $ScriptPath"
    exit 1
}

$Action = "`"$PythonExe`" `"$ScriptPath`""

schtasks /create `
    /tn $TaskName `
    /tr $Action `
    /sc WEEKLY `
    /d $TriggerDay `
    /st $TriggerTime `
    /f

if ($LASTEXITCODE -eq 0) {
    Write-Host "Registered scheduled task '$TaskName' -- runs every $TriggerDay at $TriggerTime."
    Write-Host "It will retrain the ML model, refresh the confidence calibration map,"
    Write-Host "refresh the range-timing training set, refresh per-symbol calibration"
    Write-Host "profiles, re-check LLM memorization risk, and refresh the Congress-trade"
    Write-Host "and 13F institutional-holdings caches -- no Gemini calls, ever."
    Write-Host "Logs land in data\retraining_logs\. To remove: schtasks /delete /tn `"$TaskName`" /f"
} else {
    Write-Error "schtasks failed with exit code $LASTEXITCODE -- see output above."
}
