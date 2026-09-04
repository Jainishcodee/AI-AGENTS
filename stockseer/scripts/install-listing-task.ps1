<#
    Runs the IPO listing watcher on this PC at 09:45 on weekdays.

    WHY THIS EXISTS WHEN THE CLOUD JOB ALREADY DOES IT

      The GitHub Actions listing job could not hit a 10:00 deadline. Its cron
      is best effort: a run scheduled for 08:47 IST started at 14:20, over five
      hours late, long after the listing it existed to watch. Extra cron slots
      improve the odds and guarantee nothing.

      The cloud job also cannot get live prices. Angel One's SmartAPI needs an
      Indian IP in practice, and a GitHub runner is a US datacenter, so the
      cloud watcher falls back to fifteen minute delayed quotes. On a listing
      morning the first fifteen minutes are the whole event.

      This machine has neither problem. Task Scheduler fires at the minute you
      ask for, and Angel works from your own connection.

      Keep the cloud job as the backstop. It now says plainly when it started
      too late or is running on delayed prices, so the two cannot be confused.

    WHAT IT REGISTERS

      StockSeer-Listing   09:45 Mon-Fri, wakes the PC from sleep.
                          Exits within about a second when nothing lists.
                          Runs 'ipo watch', NOT 'ipo autorun', so it does not
                          also push the IPO calendar alerts that GitHub Actions
                          already sends. Two copies of the same alert is how a
                          notification stream gets muted.

    LIMITATION YOU CANNOT CODE AROUND

      Windows can wake a SLEEPING PC. It cannot power on one that is SHUT DOWN
      or hibernated. Use Sleep, not Shut down, the night before a listing.

    RUN IT (from an ADMIN PowerShell):
      cd "g:\AI AGENTS\stockseer"
      .\scripts\install-listing-task.ps1

    REMOVE IT LATER:
      .\scripts\install-listing-task.ps1 -Uninstall

    This file is deliberately plain ASCII. PowerShell 5.1 reads a script with
    no byte-order mark as ANSI, so a smart quote or an en dash becomes mojibake
    and the parser then fails somewhere unrelated to the real problem.
#>

param(
    [switch]$Uninstall,
    [double]$Capital = 40000,
    [string]$ListingTime = "09:45"
)

$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
$listingTask = "StockSeer-Listing"

# Names the previous installer used. Cleaned up so an old calendar task cannot
# survive and double-send alerts that GitHub Actions now handles.
$legacyTasks = @("StockSeer-Calendar", "StockSeer-Dashboard")

function Assert-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    $admin = [Security.Principal.WindowsBuiltInRole]::Administrator
    if (-not $principal.IsInRole($admin)) {
        throw "Run this from an ADMIN PowerShell. Registering a wake timer needs it."
    }
}

Assert-Admin

if ($Uninstall) {
    foreach ($name in @($listingTask) + $legacyTasks) {
        if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $name -Confirm:$false
            Write-Host "removed $name"
        }
    }
    Write-Host ""
    Write-Host "Done. Listing mornings now depend on the GitHub Actions job alone,"
    Write-Host "which cannot guarantee it runs before 10:00."
    return
}

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    throw "python is not on PATH for this shell. Open a normal terminal, run 'python --version', and fix PATH first."
}
$python = $pythonCmd.Source

Write-Host "repo   : $repo"
Write-Host "python : $python"
Write-Host ""

# Remove the old calendar and dashboard tasks if they are still registered.
# GitHub Actions sends the calendar alerts now, and Jarvis polling is retired.
foreach ($name in $legacyTasks) {
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Host "removed stale task $name (superseded by GitHub Actions)"
    }
}

# Wake the machine, and do not stop the watcher because the laptop moved to
# battery or the session ran long. The market cares about neither.
#
# StartWhenAvailable matters on a laptop: if the PC was off at 09:45 and you
# open it at 09:52, the task still runs instead of being skipped until tomorrow.
$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 7) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest

# Weekdays only. NSE does not list on a Saturday, and a task that fires anyway
# trains you to ignore it.
$trigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At $ListingTime

$arguments = "-m stockseer.cli ipo watch --capital $Capital --feed auto"

$action = New-ScheduledTaskAction -Execute $python `
    -Argument $arguments -WorkingDirectory $repo

Register-ScheduledTask -TaskName $listingTask -Action $action `
    -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null

Write-Host ("registered {0,-20} {1} Mon-Fri, wakes the PC" -f $listingTask, $ListingTime)
Write-Host ""
Write-Host "------------------------------------------------------------------"
Write-Host " Leave the PC ASLEEP the night before a listing, not shut down."
Write-Host " Windows can wake a sleeping machine. It cannot power one on."
Write-Host ""
Write-Host " Alerts arrive over ntfy, so your phone does not need to be near"
Write-Host " the PC and Jarvis does not need to be open."
Write-Host ""
Write-Host " Check   : Get-ScheduledTask StockSeer-Listing"
Write-Host " Last run: (Get-ScheduledTaskInfo StockSeer-Listing).LastRunTime"
Write-Host " Test now: Start-ScheduledTask -TaskName StockSeer-Listing"
Write-Host ""
Write-Host " A test run on a day with no listing should print 'No IPO lists"
Write-Host " today' and exit within a second or two. That is success."
Write-Host "------------------------------------------------------------------"
