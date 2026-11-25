$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir server --host 0.0.0.0 --port 8443 --ssl-keyfile certs/server-key.pem --ssl-certfile certs/server.pem --no-proxy-headers --ws-max-size 8388608 --ws-per-message-deflate false
