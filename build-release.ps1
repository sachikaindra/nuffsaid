# Slim release build: app only (no models, no NVIDIA libraries). Output: release-build\NuffSaid
# Never touches dist\NuffSaid (the developer's live install).
param([string]$Python = "$PSScriptRoot\.venv-upgrade\Scripts\python.exe")
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$out = Join-Path $PSScriptRoot 'release-build'
$work = Join-Path $PSScriptRoot 'build\release'
$originalPath = $env:PATH
try {
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    & $Python -m PyInstaller --noconfirm --clean --distpath $out --workpath $work NuffSaid-Release.spec
} finally { $env:PATH = $originalPath }
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
Copy-Item -LiteralPath "$PSScriptRoot\config-portable.yaml" -Destination "$out\NuffSaid\config.yaml" -Force
Write-Host "Built $out\NuffSaid"
