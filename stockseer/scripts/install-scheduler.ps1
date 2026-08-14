<#
    Arms StockSeer to run itself on listing mornings.

    Registers two Windows scheduled tasks that can WAKE THE PC FROM SLEEP:

      StockSeer-Calendar   08:00 daily  -- queues IPO deadline alerts, exits
      StockSeer-Listing    09:40 daily  -- if something lists today, starts the
                                          dashboard and the listing watcher;
                                          otherwise exits in about a second

    IMPORTANT LIMITATION
      Windows can wake a SLEEPING PC. It cannot start one that is SHUT DOWN or
      hibernated. Use Sleep, not Shut down, the night before a listing.

    Run from an ADMIN PowerShell:
      powershell -ExecutionPolicy Bypass -File scripts\install-scheduler.ps1

    Remove everything later:
      powershell -ExecutionPolicy Bypass -File scripts\install-scheduler.ps1 -Uninstall
#>

param(
    [switch]$Uninstall,
    [double]$Capital = 40000,
    [string]$CalendarTime = "08:00",
    [string]$ListingTime = "09:40"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$calendarTask = "StockSeer-Calendar"
$listingTask = "StockSeer-Listing"

function Assert-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Run this from an ADMIN PowerShell — registering a wake timer needs it."
    }
}

Assert-Admin

if ($Uninstall) {
    foreach ($t in @($calendarTask, $listingTask)) {
        if (Get-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $t -Confirm:$false
            Write-Host "removed $t"
        }
    }
    Write-Host "`nDone. StockSeer will no longer start on its own."
    return
}

$python = (Get-Command python).Source
Write-Host "repo   : $repo"
Write-Host "python : $python`n"

# Wake the machine, and do not stop the watcher just because it runs for hours
# or the laptop is on battery -- the market does not care about either.
$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 9) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest

# --- 1. Calendar: cheap, runs every day -----------------------------------
$calAction = New-ScheduledTaskAction -Execute $python `
    -Argument "-m stockseer.cli ipo calendar --refresh --notify" `
    -WorkingDirectory $repo
$calTrigger = New-ScheduledTaskTrigger -Daily -At $CalendarTime

Register-ScheduledTask -TaskName $calendarTask -Action $calAction `
    -Trigger $calTrigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "registered $calendarTask  ($CalendarTime daily, wakes the PC)"

# --- 2. Listing morning: only does work when something actually lists ------
$listAction = New-ScheduledTaskAction -Execute $python `
    -Argument "-m stockseer.cli ipo autorun --capital $Capital" `
    -WorkingDirectory $repo
$listTrigger = New-ScheduledTaskTrigger -Daily -At $ListingTime

Register-ScheduledTask -TaskName $listingTask -Action $listAction `
    -Trigger $listTrigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "registered $listingTask   ($ListingTime daily, wakes the PC)"

# The dashboard has to be up for the phone to collect alerts, so start it with
# the machine rather than relying on it already running.
$uiTask = "StockSeer-Dashboard"
$uiAction = New-ScheduledTaskAction -Execute $python `
    -Argument "-m stockseer.cli ui --lan --no-open" -WorkingDirectory $repo
$uiTrigger = New-ScheduledTaskTrigger -AtLogOn
Register-ScheduledTask -TaskName $uiTask -Action $uiAction `
    -Trigger $uiTrigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "registered $uiTask ( at logon )"

Write-Host @"

------------------------------------------------------------------
 Two things still need to be true on a listing morning:

   1. The PC must be ASLEEP, not shut down.
      Windows can wake a sleeping machine; it cannot power one on.

   2. Jarvis must be open on your phone from ~09:55.
      Calendar alerts arrive with it closed; live price alerts cannot.

 Check what is armed:   Get-ScheduledTask StockSeer-*
 Test the listing task: Start-ScheduledTask -TaskName $listingTask
------------------------------------------------------------------
"@
