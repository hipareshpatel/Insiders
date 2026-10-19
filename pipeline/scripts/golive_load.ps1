# Load everything go-live needs onto the laptop, one step after another, with no AI call (owner, 2026-10-19; PLAN G6):
#   pwsh -File pipeline\scripts\golive_load.ps1 [-ArchivesFrom 2024-07-08] [-Since 2024-01-01]
# Needs the web dev server running (cd web; $env:CF_REMOTE_BINDINGS = '1'; npm run dev). It first waits until no
# other pipeline command is running (an audit round), so the two never share NSE's pace. Every step is safe to
# re-run: files on disk and reports already in memory are skipped, and the memory seed resumes after the last
# company it finished. Each step logs to data\logs; this script's own summary goes to data\logs\golive-<time>.log.
#
# Steps: 1 company master + universe from NSE; 2 NSE's daily price and market-cap files and corporate actions
# (data\nse\archives, raw, for prices, liquidity and price adjustment); 3 quarterly governance reports into memory;
# 4 every universe company's results and shareholding history into memory (the long one: about a day; resumable).
param(
  [string]$ArchivesFrom = '2024-07-08',   # the first day of NSE's current (UDiFF) bhavcopy format
  [string]$Since = '2024-01-01',          # quarters of results and shareholding kept in memory
  [int]$GovernancePages = 20              # NSE's governance list, 500 a page: about four quarters of every company
)
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$laptop = Join-Path $PSScriptRoot 'laptop.ps1'
$logs = Join-Path $root 'data\logs'
New-Item -ItemType Directory -Force $logs | Out-Null
$summary = Join-Path $logs ("golive-{0:yyyyMMdd-HHmm}.log" -f (Get-Date))
function Note($text) { $line = "{0:yyyy-MM-dd HH:mm:ss}  {1}" -f (Get-Date), $text; Write-Output $line; Add-Content $summary $line }

# A bulk load at 1.5-2.5 s between NSE requests (the daily path keeps 3-5 s); NSE stops us politely on a refusal
$env:NSE_PAUSE_SECONDS = '1.5,2.5'
$env:DISCOVERY_SOURCE = 'nse'
if (-not $env:UNIVERSE_MIN_MCAP_CR) { $env:UNIVERSE_MIN_MCAP_CR = '500' }

function Busy {
  @(Get-CimInstance Win32_Process -Filter "Name like 'python%'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'bse_intel' -and $_.ProcessId -ne $PID }).Count -gt 0
}
while (Busy) { Note 'another pipeline command is running; waiting 5 minutes'; Start-Sleep -Seconds 300 }

function Step($name, [scriptblock]$run) {
  Note "start: $name"
  & $run
  Note ("done:  {0} (exit {1})" -f $name, $LASTEXITCODE)
}

Step 'company master and universe (NSE)' { & pwsh -File $laptop sync-companies --source nse }
Step 'NSE archives: bhavcopy, market cap, corporate actions' {
  Push-Location (Join-Path $root 'pipeline')
  & .\.venv\Scripts\python.exe scripts\nse_archives.py --from $ArchivesFrom *>> (Join-Path $logs ("nse-archives-{0:yyyyMMdd-HHmm}.log" -f (Get-Date)))
  Pop-Location
}
Step 'governance reports into memory' {
  & pwsh -File $laptop governance-sync --pages $GovernancePages --max-files 100000 --time-budget 43200
}
# NSE refusing stops the seed with exit 0 and its place kept; three tries an hour apart, then it waits for a re-run
for ($try = 1; $try -le 3; $try++) {
  Step "results and shareholding history, every universe company (try $try)" {
    & pwsh -File $laptop seed-memory --universe --since $Since
  }
  $last = Get-ChildItem $logs -Filter 'seed-memory-*.log' | Sort-Object LastWriteTime | Select-Object -Last 1
  if (-not ($last -and (Select-String -Path $last.FullName -Pattern 'NSE refused the session' -Quiet))) { break }
  Note 'NSE refused; trying again in an hour from the same company'
  Start-Sleep -Seconds 3600
}
Note "all steps finished; summary in $summary"
