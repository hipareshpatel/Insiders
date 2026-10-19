$ErrorActionPreference = 'Stop'
Set-Location 'D:\Insiders\pipeline'
$S = '500412,544543,544936,507815,540125,532942,532891,539542,500410,541450'
for ($i = 0; $i -lt 30; $i++) {
  try { $r = Invoke-WebRequest -Uri 'http://localhost:5173/api/feed?range=all' -UseBasicParsing -TimeoutSec 10; if ($r.StatusCode -eq 200) { break } } catch { Start-Sleep 5 }
}
$env:PLATFORM_API_URL = 'http://localhost:5173'; $env:INGEST_TOKEN = 'dev-local-token'
pwsh -NoProfile -File scripts\laptop.ps1 seed-memory --scrips $S --since 2024-07-01
pwsh -NoProfile -File scripts\laptop.ps1 governance-sync --pages 4 --scrips $S --max-files 100
$env:FREE_ONLY = '1'; $env:PASS2_PACK = '6'; $env:PASS2_PACK_WAIT = '150'; $env:PIPELINE_WORKERS = '8'
pwsh -NoProfile -File scripts\laptop.ps1 backfill-companies --scrips $S --from 2026-07-15 --to 2026-10-18
