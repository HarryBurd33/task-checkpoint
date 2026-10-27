param(
  [Parameter(Mandatory=$true)][string]$Repository,
  [Parameter(Mandatory=$true)][string]$Project,
  [string]$Task,
  [string]$ProjectId
)
$ErrorActionPreference = 'Stop'
foreach ($tool in @('git','gh','codex','python')) {
  if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "Install prerequisite: $tool" }
}
if ($Repository -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$') { throw 'Use owner/repository' }
& gh auth status --hostname github.com
if ($LASTEXITCODE -ne 0) { throw 'Run gh auth login --hostname github.com on this device, then rerun.' }
& codex login status
if ($LASTEXITCODE -ne 0) { throw 'Run codex login on this device, then rerun.' }
$destination = [IO.Path]::GetFullPath($Project)
if (-not (Test-Path -LiteralPath $destination)) {
  & git clone "https://github.com/$Repository.git" $destination
  if ($LASTEXITCODE -ne 0) { throw 'Clone failed; inspect existing destination before retry.' }
}
$actual = & git -C $destination rev-parse --show-toplevel
if ($LASTEXITCODE -ne 0) { throw 'Destination is not a Git checkout' }
$actual = (Resolve-Path -LiteralPath $actual).Path
$remote = & git -C $actual remote get-url origin
if ($LASTEXITCODE -ne 0 -or ($remote -ne "https://github.com/$Repository.git" -and $remote -ne "git@github.com:$Repository.git")) { throw 'Existing checkout remote differs; preserve and review it.' }
& python (Join-Path $actual 'setup.py') status --project $actual
if ($LASTEXITCODE -ne 0) { throw 'Status inspection failed' }
$setupArgs = @((Join-Path $actual 'setup.py'),'setup','--project',$actual,'--reserve','20')
if ($Task) { $setupArgs += @('--task',$Task) }
if ($ProjectId) { $setupArgs += @('--project-id',$ProjectId) }
& python @setupArgs
if ($LASTEXITCODE -ne 0) { throw 'Setup incomplete; preserve state and inspect reported blocker.' }
Write-Host 'Review native hook trust in Codex /hooks. Verify Task Scheduler delivery and isolated synthetic threshold/readback before claiming Windows support.'
