$ErrorActionPreference = 'Stop'

$projectDir = $PSScriptRoot
$pythonExe = Join-Path $projectDir 'venv\Scripts\pythonw.exe'
$scriptFile = Join-Path $projectDir 'face_lock.py'

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}
if (-not (Test-Path -LiteralPath $scriptFile)) {
    throw "Face Lock script not found: $scriptFile"
}

$userSid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$userName = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

# Use Task Scheduler's COM API so this can be installed for the current user
# without relying on the PowerShell ScheduledTasks CIM provider.
$service = New-Object -ComObject 'Schedule.Service'
$service.Connect()
$task = $service.NewTask(0)
$task.RegistrationInfo.Description = 'Run Face Lock when this user signs in or unlocks the workstation.'
$task.Principal.UserId = $userSid
$task.Principal.LogonType = 3 # TASK_LOGON_INTERACTIVE_TOKEN
$task.Principal.RunLevel = 0 # TASK_RUNLEVEL_LUA

$logonTrigger = $task.Triggers.Create(9) # TASK_TRIGGER_LOGON
$logonTrigger.Enabled = $true
$logonTrigger.UserId = $userName

$unlockTrigger = $task.Triggers.Create(11) # TASK_TRIGGER_SESSION_STATE_CHANGE
$unlockTrigger.Enabled = $true
$unlockTrigger.StateChange = 8 # TASK_SESSION_UNLOCK
$unlockTrigger.UserId = $userName

$task.Settings.MultipleInstances = 2 # TASK_INSTANCES_IGNORE_NEW
$task.Settings.DisallowStartIfOnBatteries = $false
$task.Settings.StopIfGoingOnBatteries = $false
$task.Settings.StartWhenAvailable = $true
$task.Settings.ExecutionTimeLimit = 'PT0S'

$action = $task.Actions.Create(0) # TASK_ACTION_EXEC
$action.Path = $pythonExe
$action.Arguments = '"' + $scriptFile + '"'
$action.WorkingDirectory = $projectDir

$rootFolder = $service.GetFolder('\')
$rootFolder.RegisterTaskDefinition('FaceLockOnUnlock', $task, 6, $userSid, $null, 3, $null) | Out-Null
Write-Host 'FaceLockOnUnlock task installed for this Windows user.'
