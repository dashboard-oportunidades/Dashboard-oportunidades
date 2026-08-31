# Corre a recolha do outlet e publica o resultado no GitHub.
# Abre um browser visivel -- se aparecer um CAPTCHA resolvivel, resolve-o
# na janela; se for um bloqueio total, o script para sozinho e nao insiste.
#
# Uso: ./recolher_outlet.ps1 [categoria]
# Sem argumento, usa "base-duche". Outras categorias: monosplit

param(
    [string]$Categoria = "base-duche"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$machinePath = [System.Environment]::GetEnvironmentVariable('Path','Machine')
$userPath = [System.Environment]::GetEnvironmentVariable('Path','User')
$env:Path = $machinePath + ';' + $userPath

python recolher_outlet.py --categoria $Categoria
$exit = $LASTEXITCODE

git add docs/*.json
if (Test-Path "outlet_state.json") { git add outlet_state.json }
if (Test-Path "outlet_state_monosplit.json") { git add outlet_state_monosplit.json }
git diff --cached --quiet
$hasChanges = $LASTEXITCODE -ne 0
if ($hasChanges) {
    git commit -m "Outlet ($Categoria) de $(Get-Date -Format 'yyyy-MM-dd')"
    git push
    Write-Host "`nPublicado. A pagina atualiza-se em cerca de 1 minuto." -ForegroundColor Green
} else {
    Write-Host "`nSem alteracoes desde a ultima vez - nada para publicar." -ForegroundColor Yellow
}

if ($exit -ne 0) {
    Write-Host "`nFicaram lojas por visitar nesta corrida -- corre outra vez mais tarde para as apanhar (as ja recolhidas ficam guardadas)." -ForegroundColor Yellow
}
