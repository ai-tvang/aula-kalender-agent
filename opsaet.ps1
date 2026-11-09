# Opsætning af Aula-kalenderagenten på Windows.
# Kør fra mappen med agenten:
#   powershell -ExecutionPolicy Bypass -File .\opsaet.ps1
# Valgfrit: -Tid "07:00" -Dag Sunday -Daglig
# -KunGenveje: opretter kun den planlagte opgave og genvejene for denne mappe
#   (fx efter at agent-mappen er flyttet). Springer guiden og første kørsel over.
# Installeres normalt med én linje (se README), som henter agenten og kører dette script.

param(
    [string]$Tid = "07:00",
    [ValidateSet("Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday")]
    [string]$Dag = "Sunday",
    [switch]$Daglig,
    [switch]$Pause,
    [switch]$KunGenveje
)

$ErrorActionPreference = "Stop"
$Dir = $PSScriptRoot
# Testtilstand (kun til test af nye versioner): ingen planlagt opgave, ingen genveje, og første
# kørsel er en tørkørsel, så intet skrives i kalenderen, og der sendes ingen mail.
$Test = [bool]$env:AULA_AGENT_TEST
if ($Test) { Write-Host "TESTTILSTAND: ingen planlagt opgave, ingen genveje, første kørsel er en tørkørsel." -ForegroundColor Yellow }
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

if (-not $KunGenveje) {
# 3. AI: Claude Code eller Codex (ChatGPT), hvis ingen af dem findes, og der ikke bruges API-nøgle
function Find-Claude {
    $c = Get-Command claude -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $f = Join-Path $HOME ".local\bin\claude.exe"
    if (Test-Path $f) { return $f }
    return $null
}
function Find-Codex {
    # Samme princip som find_codex i agent.py: codex i stien, ellers npm's globale mappe.
    $c = Get-Command codex -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    foreach ($f in @((Join-Path $env:APPDATA "npm\codex.cmd"), (Join-Path $HOME ".local\bin\codex.exe"))) {
        if (Test-Path $f) { return $f }
    }
    return $null
}
function Installer-Claude {
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://claude.ai/install.ps1 | iex"
    Opdater-Sti
    $claude = Find-Claude
    if (-not $claude) {
        Write-Host "  Claude Code kunne ikke installeres. Du kan bruge en API-nøgle i stedet." -ForegroundColor Yellow
        return
    }
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
function Installer-Codex {
    # OpenAIs installationsprogram kan fejle, hvis antivirus låser den nye fil et øjeblik.
    # Derfor: ryd rester, vent og prøv igen, og brug npm som reserve.
    $releases = Join-Path $HOME ".codex\packages\standalone\releases"
    for ($forsoeg = 1; $forsoeg -le 2 -and -not (Find-Codex); $forsoeg++) {
        if ($forsoeg -gt 1) {
            Write-Host "  Prøver igen om 15 sekunder ..." -ForegroundColor Yellow
            Start-Sleep -Seconds 15
        }
        Get-ChildItem $releases -Directory -Filter ".staging.*" -Force -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://chatgpt.com/codex/install.ps1 | iex"
        Opdater-Sti
    }
    if (-not (Find-Codex) -and (Get-Command npm -ErrorAction SilentlyContinue)) {
        Write-Host "  Prøver at installere Codex med npm ..." -ForegroundColor Yellow
        npm install -g @openai/codex@latest
        Opdater-Sti
    }
    $codex = Find-Codex
    if (-not $codex) {
        Write-Host "  Codex kunne ikke installeres. Tjek i Windows-sikkerhed > Beskyttelseshistorik, om codex.exe" -ForegroundColor Yellow
        Write-Host "  er blokeret, og kør Opsætning igen. Ellers kan du vælge en API-nøgle i næste trin." -ForegroundColor Yellow
        return
    }
    Ok "Codex installeret"
    Write-Host ""
    Write-Host "  Nu skal du logge ind i Codex med din ChatGPT-konto én gang:" -ForegroundColor Cyan
    Write-Host "   1. Vælg 'Sign in with ChatGPT', hvis du bliver spurgt."
    Write-Host "   2. Log ind i browseren, der åbner. Vinduet fortsætter selv."
    Read-Host "  Tryk Enter for at logge ind" | Out-Null
    & $codex login
    if ($LASTEXITCODE -ne 0) {
        Stop-Med "Login i Codex blev ikke gennemført. Kør Opsætning fra Start-menuen (eller linjen) igen, og log ind med din ChatGPT-konto."
    }
    Ok "logget ind i Codex"
    Write-Host ""
    Write-Host "  Codex skal have en sikker sandkasse, så ChatGPT ikke kan læse dine filer." -ForegroundColor Cyan
    Write-Host "  Windows beder om godkendelse som administrator. Sig ja."
    & $codex sandbox setup --elevated --current-user
    if ($LASTEXITCODE -ne 0) {
        Stop-Med "Codex' sandkasse blev ikke sat op (godkendelsen blev måske afvist). Kør Opsætning igen og sig ja, eller vælg Claude eller en API-nøgle."
    }
    Ok "sandkassen er sat op"
    Write-Host ""
    Write-Host "  Slå træning fra i ChatGPT, så Aula-indhold ikke bruges til at træne modeller:" -ForegroundColor Cyan
    Write-Host "  chatgpt.com > Indstillinger > Datastyring > 'Gør modellen bedre for alle' = fra."
    Read-Host "  Tryk Enter, når det er gjort" | Out-Null
    $env:AULA_TRAENING_VIST = "1"
}
$mode = ""
if (Test-Path (Join-Path $Dir "config.json")) {
    try {
        $c = Get-Content (Join-Path $Dir "config.json") -Raw -Encoding UTF8 | ConvertFrom-Json
        $mode = if ($c.ai_mode) { $c.ai_mode } else { $c.claude_mode }
    } catch {}
}
$aiValg = ""
$apiValg = $false
if (-not $mode) {
    # Ny installation: spørg altid, også hvis Claude Code eller Codex allerede findes.
    Trin "AI (Claude eller ChatGPT)"
    Write-Host "  Agenten bruger en AI til at læse Aula for dig. Hver uge sendes nye opslag og beskeder"
    Write-Host "  fra Aula, også fra andre forældre og om andre børn, til den AI, du vælger."
    Write-Host "  Hvilket abonnement har du?"
    Write-Host "   1. Claude (Pro eller Max): bruger Claude Code. Det koster ikke ekstra."
    Write-Host "      Data: sendes til Anthropic og opbevares i 30 dage. Har du tilladt træning i Claudes"
    Write-Host "      privatlivsindstillinger, bruges det til træning og opbevares op til 5 år."
    Write-Host "   2. ChatGPT (Plus, Pro, Go eller Free): bruger Codex. Det koster ikke ekstra, men der er"
    Write-Host "      forbrugsgrænser. Med Go og Free bruges en mindre model, som overser flere ting."
    Write-Host "      Data: sendes til OpenAI og opbevares efter din ChatGPT-kontos vilkår. Det bruges til"
    Write-Host "      træning, medmindre du slår 'Gør modellen bedre for alle' fra (Indstillinger > Datastyring)."
    Write-Host "   3. Ingen af dem: du bruger en API-nøgle og betaler pr. kørsel (ca. 2-10 kr. om måneden)."
    Write-Host "      Data: sendes til Anthropic eller OpenAI, bruges ikke til træning og slettes efter højst 30 dage."
    Write-Host "  Ved mistanke om misbrug eller krav i loven kan udbyderne opbevare data længere. Se README."
    $standard = if ((Find-Codex) -and -not (Find-Claude)) { "2" } else { "1" }
    $svar = Read-Host "  Vælg 1, 2 eller 3 [$standard]"
    if (-not $svar) { $svar = $standard }
    if ($svar -eq "2") {
        $aiValg = "chatgpt"
        if (Find-Codex) { Ok "Codex er allerede installeret" } else { Installer-Codex }
    } elseif ($svar -eq "3") {
        $apiValg = $true
    } else {
        $aiValg = "claude"
        if (Find-Claude) { Ok "Claude Code er allerede installeret" } else { Installer-Claude }
    }
} elseif ($mode -eq "codex" -and -not (Find-Codex)) {
    Trin "ChatGPT (Codex)"
    $aiValg = "chatgpt"
    Installer-Codex
}

# 4. Pakker til agenten
uv run --python-preference only-system agent.py --help | Out-Null
if ($LASTEXITCODE -ne 0) { Stop-Med "Kunne ikke hente agentens pakker. Tjek internetforbindelsen og kør scriptet igen." }
Ok "pakker hentet"

# 5. Guiden: MitID, AI og Outlook. Børn, klasser og mailadresse findes automatisk.
if ($apiValg) { uv run --python-preference only-system agent.py opsaet --api }
elseif ($aiValg) { uv run --python-preference only-system agent.py opsaet --ai $aiValg }
else { uv run --python-preference only-system agent.py opsaet }
if ($LASTEXITCODE -ne 0) { Stop-Med "Opsætningen blev ikke færdig. Kør scriptet igen; det, der er gemt, bliver genbrugt." }
}

if (-not $Test) {
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

}

if ($KunGenveje) {
    Write-Host ""
    Write-Host "Opgaven og genvejene peger nu på $Dir." -ForegroundColor Green
} else {
# 8. Første kørsel
Trin "Første kørsel (læser de sidste 30 dage, tager 2-5 minutter)"
if ($Test) { uv run --python-preference only-system agent.py weekly --days 30 --dry-run }
else { uv run --python-preference only-system agent.py weekly --days 30 }
if ($Test -and $LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Testen er færdig. Intet er skrevet i kalenderen eller sendt. Ugemailen ligger i runs-mappen." -ForegroundColor Green
} elseif ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Opsætningen er færdig. Tjek din mail og kalenderen 'Skole og fritid' i Outlook." -ForegroundColor Green
} else {
    Write-Host ""
    Write-Host "Opsætningen er færdig, men første kørsel gav en fejl. Se ugemailen eller logs\agent.log." -ForegroundColor Yellow
}
}
if (-not $Test) { Write-Host "Senere finder du agenten i Start-menuen under 'Aula-kalenderagent'." }
if ($Pause) { Read-Host "Tryk Enter for at lukke" | Out-Null }
