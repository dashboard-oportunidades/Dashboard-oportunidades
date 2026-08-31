# Corre a verificação de preços a partir deste PC e publica o resultado no GitHub.
# Usa isto porque o GitHub Actions (na nuvem) é bloqueado pelo Datadome do site;
# a partir de casa passa sem problemas.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$envFile = Join-Path $PSScriptRoot ".env"
if (-not (Test-Path $envFile)) {
    Write-Error "Falta o ficheiro .env. Copia .env.example para .env e preenche os valores."
    exit 1
}

Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([^#=]+?)\s*=\s*(.*)\s*$') {
        [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
    }
}

python monitor.py
if ($LASTEXITCODE -ne 0) {
    Write-Error "monitor.py falhou (código $LASTEXITCODE). Não vou fazer commit."
    exit $LASTEXITCODE
}

git add state.json docs/data.json
$staged = git diff --cached --quiet; $hasChanges = $LASTEXITCODE -ne 0
if ($hasChanges) {
    git commit -m "Preços de $(Get-Date -Format 'yyyy-MM-dd')"
    git push
    Write-Host "`nPublicado. A página atualiza-se em ~1 minuto." -ForegroundColor Green
} else {
    Write-Host "`nSem alterações de preço desde a última vez — nada para publicar." -ForegroundColor Yellow
}
