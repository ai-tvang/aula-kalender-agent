# Installation af Aula-kalenderagenten med én linje i PowerShell:
#   irm https://raw.githubusercontent.com/ai-tvang/aula-kalender-agent/main/install.ps1 | iex
#
# Henter agenten til C:\Users\<dig>\Aula-kalenderagent og starter opsætningen.
# Findes agenten allerede (fx et andet sted fra en ZIP-installation), opdateres den dér.
# Kører du linjen igen, opdateres agenten. Dine indstillinger og login bevares,
# fordi de ikke findes i ZIP-filen.

& {
    $ErrorActionPreference = "Stop"
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    $Repo = "ai-tvang/aula-kalender-agent"
    $Branch = "main"
    if ($env:AULA_AGENT_BRANCH) { $Branch = $env:AULA_AGENT_BRANCH }  # kun til test af nye versioner
    # Mappe: AULA_AGENT_DIR, ellers den mappe, den planlagte opgave allerede bruger
    # (så en opdatering rammer den eksisterende installation), ellers standard.
    $Dir = Join-Path $HOME "Aula-kalenderagent"
    if ($env:AULA_AGENT_DIR) {
        $Dir = $env:AULA_AGENT_DIR
    } else {
        try {
            $opgave = Get-ScheduledTask -TaskName "Aula-kalenderagent ugentlig" -ErrorAction Stop
            $wd = $opgave.Actions[0].WorkingDirectory
            if ($wd -and (Test-Path (Join-Path $wd "agent.py"))) { $Dir = $wd }
        } catch {}
    }

    Write-Host ""
    Write-Host "Aula-kalenderagent" -ForegroundColor Cyan
    Write-Host "Agenten installeres i $Dir"

    if ($Dir -match "OneDrive") {
        Write-Host "STOP: Din brugermappe ligger i OneDrive. Hent ZIP-filen og læg den uden for OneDrive (se README)." -ForegroundColor Red
        return
    }

    $opdatering = Test-Path (Join-Path $Dir "config.json")

    # 1. Hent den nyeste version
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("aula-kalenderagent-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        $zip = Join-Path $tmp "agent.zip"
        Write-Host "Henter agenten fra GitHub ..."
        $ProgressPreference = "SilentlyContinue"
        Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/$Repo/archive/refs/heads/$Branch.zip" -OutFile $zip
        Expand-Archive -Path $zip -DestinationPath $tmp -Force
        $src = Get-ChildItem -Path $tmp -Directory | Select-Object -First 1
        if (-not $src) { throw "ZIP-filen var tom." }
        New-Item -ItemType Directory -Path $Dir -Force | Out-Null
        Copy-Item -Path (Join-Path $src.FullName "*") -Destination $Dir -Recurse -Force
    } catch {
        Write-Host "STOP: Kunne ikke hente agenten: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "Tjek internetforbindelsen og prøv igen." -ForegroundColor Red
        return
    } finally {
        Remove-Item -Path $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
    Get-ChildItem -Path $Dir -Recurse -File | Unblock-File -ErrorAction SilentlyContinue
    Write-Host "  OK: agenten ligger i $Dir" -ForegroundColor Green

    # 2. Opsætning (eller kun opdatering)
    if ($opdatering) {
        Write-Host ""
        Write-Host "Agenten er opdateret. Dine indstillinger og login er bevaret." -ForegroundColor Green
        $svar = Read-Host "Vil du også køre opsætningen igen, fx efter nyt skoleår? [j/N]"
        if ($svar -notmatch '^(j|ja|y|yes)$') { return }
    }
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Dir "opsaet.ps1")
}
