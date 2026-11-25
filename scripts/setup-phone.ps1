param([Parameter(Mandatory=$true)][string]$LanIP)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
& .\.venv\Scripts\python.exe -m pip install -r scripts\requirements.txt
if($LASTEXITCODE -ne 0){throw 'Dependency installation failed'}
& .\.venv\Scripts\python.exe scripts\phone_cert.py $LanIP
if($LASTEXITCODE -ne 0){throw 'Certificate generation failed'}
Push-Location student-app
try { & npm.cmd run build; if($LASTEXITCODE -ne 0){throw 'Student build failed'} } finally { Pop-Location }
