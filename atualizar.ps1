# Corre a verificacao de precos a partir deste PC e publica o resultado no GitHub.
# Usa isto porque o GitHub Actions (na nuvem) e bloqueado pelo Datadome do site;
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
    Write-Error "monitor.py falhou (codigo $LASTEXITCODE). Nao vou fazer commit."
    exit $LASTEXITCODE
}

git add state.json docs/data.json
git diff --cached --quiet
$hasChanges = $LASTEXITCODE -ne 0
if ($hasChanges) {
    git commit -m "Precos de $(Get-Date -Format 'yyyy-MM-dd')"
    git push
    Write-Host "`nPublicado. A pagina atualiza-se em cerca de 1 minuto." -ForegroundColor Green
} else {
    Write-Host "`nSem alteracoes de preco desde a ultima vez - nada para publicar." -ForegroundColor Yellow
}
