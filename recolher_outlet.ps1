# Corre a recolha do outlet e publica o resultado no GitHub.
# Abre um browser visivel -- se aparecer um CAPTCHA resolvivel, resolve-o
# na janela; se for um bloqueio total, o script para sozinho e nao insiste.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

python recolher_outlet.py
$exit = $LASTEXITCODE

git add docs/outlet.json
git diff --cached --quiet
$hasChanges = $LASTEXITCODE -ne 0
if ($hasChanges) {
    git commit -m "Outlet de $(Get-Date -Format 'yyyy-MM-dd')"
    git push
    Write-Host "`nPublicado. A pagina atualiza-se em cerca de 1 minuto." -ForegroundColor Green
} else {
    Write-Host "`nSem alteracoes desde a ultima vez - nada para publicar." -ForegroundColor Yellow
}

if ($exit -ne 0) {
    Write-Host "`nAviso: o recolher_outlet.py parou mais cedo (bloqueio ou erro). O que tinha sido recolhido ate la ja foi publicado acima." -ForegroundColor Yellow
}
