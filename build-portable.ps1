param([string]$Python = "$PSScriptRoot\.venv-upgrade\Scripts\python.exe")
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$savedData = $null
if (Test-Path -LiteralPath "$PSScriptRoot\dist\NuffSaid\data") {
    $savedData = Join-Path $PSScriptRoot ('backups\portable-data-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    New-Item -ItemType Directory -Path $savedData -Force | Out-Null
    Copy-Item -LiteralPath "$PSScriptRoot\dist\NuffSaid\data" -Destination $savedData -Recurse
    Copy-Item -LiteralPath "$PSScriptRoot\dist\NuffSaid\config.yaml" -Destination $savedData
}
foreach ($modelName in @('base', 'turbo')) {
    if (-not (Test-Path -LiteralPath "$PSScriptRoot\models\$modelName\model.bin")) {
        throw "Download models/$modelName before building."
    }
}
$originalPath = $env:PATH
$staging = Join-Path $PSScriptRoot ('build-staging\' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
try {
    # Avoid collecting unrelated ICU DLLs from development tools on PATH.
    # Qt requires Windows' unversioned ICU API, not a different tool's ICU build.
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot"
    & $Python -m PyInstaller --noconfirm --distpath $staging NuffSaid.spec
} finally {
    $env:PATH = $originalPath
}
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
New-Item -ItemType Directory -Path "$PSScriptRoot\dist\NuffSaid" -Force | Out-Null
Get-ChildItem -LiteralPath "$staging\NuffSaid" | Copy-Item -Destination "$PSScriptRoot\dist\NuffSaid" -Recurse -Force
if (-not (Test-Path -LiteralPath "$PSScriptRoot\dist\NuffSaid\config.yaml")) {
    Copy-Item -LiteralPath "$PSScriptRoot\config-portable.yaml" -Destination "$PSScriptRoot\dist\NuffSaid\config.yaml"
}
Copy-Item -LiteralPath "$PSScriptRoot\PORTABLE_README.txt" -Destination "$PSScriptRoot\dist\NuffSaid\README.txt"
New-Item -ItemType Directory -Path "$PSScriptRoot\dist\NuffSaid\models" -Force | Out-Null
Copy-Item -LiteralPath "$PSScriptRoot\models\base" -Destination "$PSScriptRoot\dist\NuffSaid\models" -Recurse -Force
Copy-Item -LiteralPath "$PSScriptRoot\models\turbo" -Destination "$PSScriptRoot\dist\NuffSaid\models" -Recurse -Force
New-Item -ItemType File -Path "$PSScriptRoot\dist\NuffSaid\portable.flag" -Force | Out-Null
New-Item -ItemType Directory -Path "$PSScriptRoot\dist\NuffSaid\source" -Force | Out-Null
foreach ($source in @('run_flow.py', 'run.py', 'speech_runtime.py', 'personal_store.py', 'desktop_services.py', 'recovery_ui.py', 'native_shortcuts.py', 'instance_guard.py', 'requirements-upgrade.txt', 'build-portable.ps1', 'NuffSaid.spec', 'config-portable.yaml', 'PORTABLE_README.txt')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $source) -Destination "$PSScriptRoot\dist\NuffSaid\source"
}
Copy-Item -LiteralPath "$PSScriptRoot\assets" -Destination "$PSScriptRoot\dist\NuffSaid\source" -Recurse -Force
Write-Host 'Built dist\NuffSaid. Run NuffSaid.exe --self-test before zipping for release.'
