# Kører en eller flere af agentens kommandoer og holder vinduet åbent bagefter.
# Bruges af genvejene i Start-menuen, fx:
#   powershell -ExecutionPolicy Bypass -File .\koer.ps1 login-aula weekly

Set-Location $PSScriptRoot
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
            [Environment]::GetEnvironmentVariable("Path", "User") + ";" +
            (Join-Path $HOME ".local\bin")

$navne = @{
    "weekly" = "Læser Aula og opdaterer kalenderen"
    "login-aula" = "Nyt MitID-login til Aula. Godkend i MitID-appen."
    "login-outlook" = "Nyt Outlook-login"
}
$fejl = $false
foreach ($kommando in $args) {
    Write-Host ""
    $titel = $navne[$kommando]
    if (-not $titel) { $titel = $kommando }
    Write-Host "== $titel" -ForegroundColor Cyan
    uv run --python-preference only-system agent.py $kommando
    if ($LASTEXITCODE -ne 0) { $fejl = $true; break }
}
Write-Host ""
if ($fejl) {
    Write-Host "Noget gik galt. Se teksten ovenfor eller logs\agent.log." -ForegroundColor Yellow
} else {
    Write-Host "Færdig." -ForegroundColor Green
}
Read-Host "Tryk Enter for at lukke" | Out-Null
