# Run one pipeline command on the laptop against the local site, logging to data\logs.
#   pwsh -File pipeline\scripts\laptop.ps1 backfill-companies --scrips 506525,532776,505192,500672,530019
#   pwsh -File pipeline\scripts\laptop.ps1 sync-companies
# Needs the web dev server running (cd web; $env:CF_REMOTE_BINDINGS = '1'; npm run dev).
# Keys come from C:\Users\Quali\insiders-keys.ps1 and are never printed.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location (Join-Path $root 'pipeline')
. C:\Users\Quali\insiders-keys.ps1
foreach ($k in 'GROQ_API_KEY', 'NVIDIA_API_KEY', 'MISTRAL_API_KEY', 'ZAI_API_KEY', 'GEMINI_API_KEY', 'OPENROUTER_API_KEY', 'DEEPSEEK_API_KEY') {
  if (Test-Path "env:$k") { Set-Item "env:$k" ((Get-Item "env:$k").Value.Trim()) }  # a stray space breaks auth
}
$env:BSE_INTEL_SINK = 'platform'
$env:PLATFORM_API_URL = 'http://localhost:5173'
$env:INGEST_TOKEN = 'dev-local-token'
$env:PYTHONIOENCODING = 'utf-8'
if (-not $env:PIPELINE_WORKERS) { $env:PIPELINE_WORKERS = '5' }  # decision D18
$logs = Join-Path $root 'data\logs'
New-Item -ItemType Directory -Force $logs | Out-Null
$log = Join-Path $logs ("{0}-{1:yyyyMMdd-HHmm}.log" -f $args[0], (Get-Date))
Write-Output "logging to $log"
& .\.venv\Scripts\python.exe -m bse_intel @args *> $log
exit $LASTEXITCODE
