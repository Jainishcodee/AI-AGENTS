<#
    Arms StockSeer to run itself, so nothing depends on you remembering.

    Registers three Windows scheduled tasks. All of them can WAKE THE PC FROM
    SLEEP:

      StockSeer-Dashboard  at logon     the web server, so Jarvis always has
                                        something to reach
      StockSeer-Calendar   08:00 daily  queues IPO deadline alerts, then exits
      StockSeer-Listing    09:40 daily  if something lists today, starts the
                                        watcher; otherwise exits in a second

    LIMITATION
      Windows can wake a SLEEPING PC. It cannot power on one that is SHUT DOWN
      or hibernated. Use Sleep, not Shut down, the night before a listing.

    RUN IT (from an ADMIN PowerShell):
      cd "g:\AI AGENTS\stockseer"
      .\scripts\install-scheduler.ps1

    REMOVE EVERYTHING LATER:
      .\scripts\install-scheduler.ps1 -Uninstall

    This file is deliberately plain ASCII. PowerShell 5.1 reads a script with
    no byte-order mark as ANSI, so any smart quote or dash becomes mojibake and
    the parser fails somewhere unrelated to the real problem.
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
$uiTask = "StockSeer-Dashboard"

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
    foreach ($name in @($calendarTask, $listingTask, $uiTask)) {
        if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $name -Confirm:$false
            Write-Host "removed $name"
        }
    }
    Write-Host ""
    Write-Host "Done. StockSeer will no longer start on its own."
    return
}

$python = (Get-Command python).Source
Write-Host "repo   : $repo"
Write-Host "python : $python"
Write-Host ""

# Wake the machine, and do not stop the watcher just because it runs for hours
# or the laptop moves to battery. The market cares about neither.
$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 9) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest

function Register-One {
    param($Name, $Arguments, $Trigger, $Label)

    $action = New-ScheduledTaskAction -Execute $python `
        -Argument $Arguments -WorkingDirectory $repo

    Register-ScheduledTask -TaskName $Name -Action $action `
        -Trigger $Trigger -Settings $settings -Principal $principal -Force | Out-Null

    Write-Host ("registered {0,-22} {1}" -f $Name, $Label)
}

# 1. The dashboard. Without this running, Jarvis has nothing to poll.
Register-One -Name $uiTask `
    -Arguments "-m stockseer.cli ui --lan --no-open" `
    -Trigger (New-ScheduledTaskTrigger -AtLogOn) `
    -Label "at logon"

# 2. Calendar. Cheap, runs every day, needs no market feed.
Register-One -Name $calendarTask `
    -Arguments "-m stockseer.cli ipo calendar --refresh --notify" `
    -Trigger (New-ScheduledTaskTrigger -Daily -At $CalendarTime) `
    -Label "$CalendarTime daily, wakes the PC"

# 3. Listing morning. Exits in about a second when nothing lists.
Register-One -Name $listingTask `
    -Arguments "-m stockseer.cli ipo autorun --capital $Capital" `
    -Trigger (New-ScheduledTaskTrigger -Daily -At $ListingTime) `
    -Label "$ListingTime daily, wakes the PC"

Write-Host ""
Write-Host "------------------------------------------------------------------"
Write-Host " Two things still have to be true on a listing morning:"
Write-Host ""
Write-Host "   1. The PC must be ASLEEP, not shut down."
Write-Host "      Windows can wake a sleeping machine; it cannot power one on."
Write-Host ""
Write-Host "   2. Jarvis open on your phone from about 09:55, for live price"
Write-Host "      alerts. Calendar alerts arrive with it closed."
Write-Host ""
Write-Host " If ntfy is configured, alerts reach you even with all of the above"
Write-Host " switched off. That is the safety net."
Write-Host ""
Write-Host " Check:  Get-ScheduledTask StockSeer-*"
Write-Host " Test :  Start-ScheduledTask -TaskName $listingTask"
Write-Host "------------------------------------------------------------------"
