param([Parameter(Mandatory=$true)][string]$LanIP)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
& .\.venv\Scripts\python.exe -m http.server 8081 --bind $LanIP --directory certs/public
