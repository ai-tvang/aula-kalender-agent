# Opsætning af Aula-kalenderagenten på Windows.
# Kør fra mappen med agenten:
#   powershell -ExecutionPolicy Bypass -File .\opsaet.ps1
# Valgfrit: -Tid "07:00" -Dag Sunday -Daglig
# Installeres normalt med én linje (se README), som henter agenten og kører dette script.

param(
    [string]$Tid = "07:00",
    [ValidateSet("Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday")]
    [string]$Dag = "Sunday",
    [switch]$Daglig,
    [switch]$Pause
)

$ErrorActionPreference = "Stop"
$Dir = $PSScriptRoot
Set-Location $Dir

function Trin($tekst) { Write-Host ""; Write-Host "== $tekst" -ForegroundColor Cyan }
function Ok($tekst) { Write-Host "  OK: $tekst" -ForegroundColor Green }
function Stop-Med($tekst) {
    Write-Host ""; Write-Host "STOP: $tekst" -ForegroundColor Red
    if ($Pause) { Read-Host "Tryk Enter for at lukke" | Out-Null }
    exit 1
}
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

# 3. Claude Code (hvis den mangler, og der ikke allerede bruges en API-nøgle)
function Find-Claude {
    $c = Get-Command claude -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $f = Join-Path $HOME ".local\bin\claude.exe"
    if (Test-Path $f) { return $f }
    return $null
}
$brugerApi = $false
if (Test-Path (Join-Path $Dir "config.json")) {
    try { $brugerApi = ((Get-Content (Join-Path $Dir "config.json") -Raw -Encoding UTF8 | ConvertFrom-Json).claude_mode -eq "api") } catch {}
}
if (-not (Find-Claude) -and -not $brugerApi) {
    Trin "Claude"
    Write-Host "  Agenten bruger Claude til at læse Aula for dig. Har du et betalt Claude-abonnement"
    Write-Host "  (Pro eller Max), er Claude Code den nemmeste vej, og det koster ikke ekstra."
    Write-Host "  Uden abonnement bruger du i stedet en API-nøgle (ca. 6-10 kr. om måneden)."
    $svar = Read-Host "  Har du et Claude-abonnement, og skal Claude Code installeres nu? [J/n]"
    if ($svar -notmatch '^(n|nej|no)$') {
        powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://claude.ai/install.ps1 | iex"
        Opdater-Sti
        $claude = Find-Claude
        if (-not $claude) {
            Write-Host "  Claude Code kunne ikke installeres. Du kan bruge en API-nøgle i stedet." -ForegroundColor Yellow
        } else {
            Ok "Claude Code installeret"
            Write-Host ""
            Write-Host "  Nu skal du logge ind i Claude Code én gang:" -ForegroundColor Cyan
            Write-Host "   1. Svar på de få spørgsmål (Enter er fint), og vælg login med dit Claude-abonnement."
            Write-Host "   2. Log ind i browseren, der åbner."
            Write-Host "   3. Når Claude Code er klar, skriv /exit og tryk Enter. Så fortsætter opsætningen."
            Read-Host "  Tryk Enter for at starte Claude Code" | Out-Null
            & $claude
            Ok "Claude Code er klar"
        }
    }
}

# 4. Pakker til agenten
uv run --python-preference only-system agent.py --help | Out-Null
if ($LASTEXITCODE -ne 0) { Stop-Med "Kunne ikke hente agentens pakker. Tjek internetforbindelsen og kør scriptet igen." }
Ok "pakker hentet"

# 5. Guiden: MitID, Claude og Outlook. Børn, klasser og mailadresse findes automatisk.
uv run --python-preference only-system agent.py opsaet
if ($LASTEXITCODE -ne 0) { Stop-Med "Opsætningen blev ikke færdig. Kør scriptet igen; det, der er gemt, bliver genbrugt." }

# 6. Planlagt opgave
Trin "Automatisk kørsel"
$uvSti = (Get-Command uv).Source
$settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$a = New-ScheduledTaskAction -Execute $uvSti -Argument "run --python-preference only-system agent.py weekly" -WorkingDirectory $Dir
$t = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Dag -At $Tid
Register-ScheduledTask -TaskName "Aula-kalenderagent ugentlig" -Action $a -Trigger $t -Settings $settings -Force | Out-Null
$dagDk = @{Monday="mandag";Tuesday="tirsdag";Wednesday="onsdag";Thursday="torsdag";Friday="fredag";Saturday="lørdag";Sunday="søndag"}[$Dag]
Ok "Agenten kører hver $dagDk kl. $Tid. Er computeren slukket, kører den, så snart du tænder den."
if ($Daglig) {
    $a2 = New-ScheduledTaskAction -Execute $uvSti -Argument "run --python-preference only-system agent.py daily" -WorkingDirectory $Dir
    $t2 = New-ScheduledTaskTrigger -Daily -At "09:30"
    Register-ScheduledTask -TaskName "Aula-kalenderagent daglig" -Action $a2 -Trigger $t2 -Settings $settings -Force | Out-Null
    Ok "Daglig opgave oprettet"
}

# 7. Genveje i Start-menuen, så terminalen ikke er nødvendig bagefter
Trin "Genveje"
try {
    $menu = Join-Path ([Environment]::GetFolderPath("Programs")) "Aula-kalenderagent"
    New-Item -ItemType Directory -Path $menu -Force | Out-Null
    $ps = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $koer = Join-Path $Dir "koer.ps1"
    $shell = New-Object -ComObject WScript.Shell
    function Ny-Genvej($navn, $maal, $argumenter, $beskrivelse) {
        $g = $shell.CreateShortcut((Join-Path $menu "$navn.lnk"))
        $g.TargetPath = $maal
        $g.Arguments = $argumenter
        $g.WorkingDirectory = $Dir
        $g.Description = $beskrivelse
        $g.Save()
    }
    Ny-Genvej "Kør nu" $ps "-NoProfile -ExecutionPolicy Bypass -File `"$koer`" weekly" "Læs Aula og opdater kalenderen nu"
    Ny-Genvej "Log ind på Aula igen" $ps "-NoProfile -ExecutionPolicy Bypass -File `"$koer`" login-aula weekly" "Nyt MitID-login, når Aula-login er udløbet"
    Ny-Genvej "Log ind på Outlook igen" $ps "-NoProfile -ExecutionPolicy Bypass -File `"$koer`" login-outlook weekly" "Nyt Outlook-login"
    Ny-Genvej "Opsætning" $ps "-NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $Dir 'opsaet.ps1')`" -Pause" "Kør opsætningen igen, fx efter nyt skoleår"
    Ny-Genvej "Åbn agent-mappen" (Join-Path $env:SystemRoot "explorer.exe") "`"$Dir`"" "Indstillinger, regler og log"
    Ok "Start-menuen > Aula-kalenderagent: Kør nu, Log ind på Aula igen, Opsætning m.fl."
} catch {
    Write-Host "  Genvejene kunne ikke oprettes ($($_.Exception.Message)). Agenten virker stadig." -ForegroundColor Yellow
}

# 8. Første kørsel
Trin "Første kørsel (læser de sidste 30 dage, tager 2-5 minutter)"
uv run --python-preference only-system agent.py weekly --days 30
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Opsætningen er færdig. Tjek din mail og kalenderen 'Skole og fritid' i Outlook." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Opsætningen er færdig, men første kørsel gav en fejl. Se ugemailen eller logs\agent.log." -ForegroundColor Yellow
}
Write-Host "Senere finder du agenten i Start-menuen under 'Aula-kalenderagent'."
if ($Pause) { Read-Host "Tryk Enter for at lukke" | Out-Null }
