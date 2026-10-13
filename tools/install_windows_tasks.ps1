param([switch]$VerifyOnly)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = (Get-Command pythonw.exe -ErrorAction Stop).Source
$taskUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$taskStart = [datetime]'2026-10-13T09:00:00'
if (-not $VerifyOnly) {
    $taskPrincipal = New-ScheduledTaskPrincipal -UserId $taskUser -LogonType Interactive -RunLevel Limited
    $taskSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 12) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -WakeToRun
    foreach ($taskMode in @('send','read')) {
        $taskName = if ($taskMode -eq 'send') {'Xunpan-Inquiry-Send'} else {'Xunpan-Reply-Scan'}
        if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) { throw "Task already exists: $taskName; review before replacing." }
        $taskAction = New-ScheduledTaskAction -Execute $taskPython -Argument ('-X utf8 "'+(Join-Path $taskRoot 'tools\scheduled.py')+'" '+$taskMode) -WorkingDirectory $taskRoot
        $taskTrigger = New-ScheduledTaskTrigger -Daily -At $taskStart
        if ($taskMode -eq 'read') {
            $taskRepeat = New-ScheduledTaskTrigger -Once -At $taskStart -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration (New-TimeSpan -Hours 10)
            $taskTrigger.Repetition = $taskRepeat.Repetition
        }
        $taskDescription = if ($taskMode -eq 'send') {'09:00 Beijing: Japan non-food-contact products; latest multiple >2; stop at 18:00; Feishu notifications.'} else {'09:00-18:59 Beijing every 10 minutes: read replies, record quotes and update Japan review; daily report at 18:00.'}
        Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger $taskTrigger -Settings $taskSettings -Principal $taskPrincipal -Description $taskDescription | Out-Null
    }
}
foreach ($taskName in @('Xunpan-Inquiry-Send','Xunpan-Reply-Scan')) {
    $task = Get-ScheduledTask -TaskName $taskName
    $taskInfo = Get-ScheduledTaskInfo -TaskName $taskName
    [pscustomobject]@{Name=$taskName;State=[string]$task.State;Enabled=$task.Settings.Enabled;Start=$task.Triggers[0].StartBoundary;NextRun=$taskInfo.NextRunTime;Interval=$task.Triggers[0].Repetition.Interval;Duration=$task.Triggers[0].Repetition.Duration;LastResult=$taskInfo.LastTaskResult;User=$task.Principal.UserId;LogonType=$task.Principal.LogonType;Execute=$task.Actions.Execute;Arguments=$task.Actions.Arguments}
}
