$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
New-Item -ItemType Directory -Force -Path tools | Out-Null
$binary=Join-Path (Get-Location) 'tools\cloudflared.exe'
if(!(Test-Path -LiteralPath $binary)){
    $release=Invoke-RestMethod -Uri 'https://api.github.com/repos/cloudflare/cloudflared/releases/latest'
    $asset=$release.assets | Where-Object name -eq 'cloudflared-windows-amd64.exe' | Select-Object -First 1
    if(!$asset -or !$asset.digest -or !$asset.digest.StartsWith('sha256:')){throw 'Cannot verify official download digest'}
    $temporary=$binary+'.download'
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $temporary
    $actual=(Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash.ToLowerInvariant()
    if($actual -ne $asset.digest.Substring(7)){Remove-Item -LiteralPath $temporary;throw 'Download checksum mismatch'}
    Move-Item -LiteralPath $temporary -Destination $binary
}
& $binary tunnel --url http://127.0.0.1:8766
