# Opsætning af Aula-kalenderagenten på Windows.
# Kør fra mappen med agenten:
#   powershell -ExecutionPolicy Bypass -File .\opsaet.ps1
# Valgfrit: -Tid "07:00" -Dag Sunday -Daglig

param(
    [string]$Tid = "07:00",
    [ValidateSet("Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday")]
    [string]$Dag = "Sunday",
    [switch]$Daglig
)

$ErrorActionPreference = "Stop"
$Dir = $PSScriptRoot
Set-Location $Dir

function Trin($tekst) { Write-Host ""; Write-Host "== $tekst" -ForegroundColor Cyan }
function Ok($tekst) { Write-Host "  OK: $tekst" -ForegroundColor Green }
function Stop-Med($tekst) { Write-Host ""; Write-Host "STOP: $tekst" -ForegroundColor Red; exit 1 }
function Opdater-Sti {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User") + ";" +
                (Join-Path $HOME ".local\bin")
}
# 1. Python 3.14 fra python.org
# (uv's egen Python kan blive blokeret af Windows' Intelligent appkontrol,
#  derfor bruges den officielle, signerede Python.)
Trin "Forbereder (Python og uv, kan tage et par minutter første gang)"
$harPython = $false
try { $v = & py -3.14 --version 2>$null; if ($LASTEXITCODE -eq 0) { $harPython = $true } } catch {}
if (-not $harPython) {
    winget install --id Python.Python.3.14 -e --accept-source-agreements --accept-package-agreements
    Opdater-Sti
    try { $v = & py -3.14 --version } catch { Stop-Med "Python 3.14 kunne ikke installeres. Installer den fra python.org og kør scriptet igen." }
}
Ok $v

# 2. uv
Opdater-Sti
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    Opdater-Sti
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Stop-Med "uv kunne ikke installeres. Se https://docs.astral.sh/uv/ og kør scriptet igen." }
Ok (uv --version)

# 3. Pakker til agenten
uv run --python-preference only-system agent.py --help | Out-Null
if ($LASTEXITCODE -ne 0) { Stop-Med "Kunne ikke hente agentens pakker. Tjek internetforbindelsen og kør scriptet igen." }
Ok "pakker hentet"

# 4. Guiden: MitID, Claude og Outlook. Børn, klasser og mailadresse findes automatisk.
uv run --python-preference only-system agent.py opsaet
if ($LASTEXITCODE -ne 0) { Stop-Med "Opsætningen blev ikke færdig. Kør scriptet igen; det, der er gemt, bliver genbrugt." }

# 5. Planlagt opgave
Trin "Automatisk kørsel"
$uvSti = (Get-Command uv).Source
$settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$a = New-ScheduledTaskAction -Execute $uvSti -Argument "run --python-preference only-system agent.py weekly" -WorkingDirectory $Dir
$t = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Dag -At $Tid
Register-ScheduledTask -TaskName "Aula-kalenderagent ugentlig" -Action $a -Trigger $t -Settings $settings -Force | Out-Null
$dagDk = @{Monday="mandag";Tuesday="tirsdag";Wednesday="onsdag";Thursday="torsdag";Friday="fredag";Saturday="lørdag";Sunday="søndag"}[$Dag]
Ok "Agenten kører hver $dagDk kl. $Tid. Computeren må gerne være i dvale, men ikke slukket."
if ($Daglig) {
    $a2 = New-ScheduledTaskAction -Execute $uvSti -Argument "run --python-preference only-system agent.py daily" -WorkingDirectory $Dir
    $t2 = New-ScheduledTaskTrigger -Daily -At "09:30"
    Register-ScheduledTask -TaskName "Aula-kalenderagent daglig" -Action $a2 -Trigger $t2 -Settings $settings -Force | Out-Null
    Ok "Daglig opgave oprettet"
}

# 6. Første kørsel
Trin "Første kørsel (læser de sidste 30 dage, tager 2-5 minutter)"
uv run --python-preference only-system agent.py weekly --days 30
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Opsætningen er færdig. Tjek din mail og kalenderen 'Skole og fritid' i Outlook." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Opsætningen er færdig, men første kørsel gav en fejl. Se ugemailen eller logs\agent.log." -ForegroundColor Yellow
}
