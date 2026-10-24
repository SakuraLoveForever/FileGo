# FileGo daily auto commit + push.
#
# Registered as the Windows scheduled task "FileGo-DailyPush" (every day 00:00).
# It commits every change (respecting .gitignore) as an "auto snapshot" commit and
# pushes the current branch to origin. When there is nothing to commit it exits
# without touching git history; when an earlier push failed it still retries,
# because the push step depends on "local ahead of origin", not on new changes.
#
# Log: %LOCALAPPDATA%\FileGo\auto_push.log
# Keep this file ASCII-only: Windows PowerShell 5.1 reads scripts as ANSI, and
# non-ASCII comment text can break parsing on some systems.

$ErrorActionPreference = "Continue"

$repoRoot = Split-Path -Parent $PSScriptRoot
$logDir   = Join-Path $env:LOCALAPPDATA "FileGo"
$logFile  = Join-Path $logDir "auto_push.log"

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

function Write-Log([string]$Message) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

function Fail([string]$Message) {
    Write-Log "ERROR: $Message"
    exit 1
}

# Never wait for interactive credentials when nobody is at the keyboard.
$env:GIT_TERMINAL_PROMPT = "0"
$env:GCM_INTERACTIVE = "never"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail "git not found in PATH"
}
if (-not (Test-Path (Join-Path $repoRoot ".git"))) {
    Fail "not a git repository: $repoRoot"
}

# symbolic-ref works on an unborn HEAD (fresh repo, no commits yet); rev-parse does not.
$branch = & git -C $repoRoot symbolic-ref --short -q HEAD 2>$null
if (-not $branch) {
    Fail "detached HEAD, cannot push"
}

# 1) Snapshot local changes. Ignored files (build output, __pycache__, ...) are skipped.
$status = & git -C $repoRoot status --porcelain 2>$null
if ($status) {
    & git -C $repoRoot add -A 2>$null | Out-Null
    $staged = & git -C $repoRoot diff --cached --name-only 2>$null
    if ($staged) {
        $stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
        & git -C $repoRoot commit -m "auto snapshot: $stamp" 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Fail "git commit failed with exit code $LASTEXITCODE"
        }
        Write-Log ("committed {0} changed file(s)" -f (($staged | Measure-Object).Count))
    }
    else {
        Write-Log "only ignored files changed, nothing to commit"
    }
}
else {
    Write-Log "no local changes"
}

# 2) Push when the local branch is ahead of origin. This also retries a push that
#    failed on an earlier day even if nothing has changed since then.
$hasRemote = & git -C $repoRoot rev-parse --verify --quiet "origin/$branch" 2>$null
$ahead = 0
if ($hasRemote) {
    $cnt = & git -C $repoRoot rev-list --count "origin/$branch..HEAD" 2>$null
    if ($cnt) {
        $ahead = [int]$cnt
    }
}
else {
    $ahead = 1
}

if ($ahead -eq 0) {
    Write-Log "nothing to push, origin/$branch is up to date"
    exit 0
}

& git -C $repoRoot push origin $branch 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Log "push rejected, retrying after pull --rebase --autostash"
    & git -C $repoRoot pull --rebase --autostash origin $branch 2>$null | Out-Null
    & git -C $repoRoot push origin $branch 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Fail "git push failed; $ahead commit(s) stay local and will be retried tomorrow"
    }
}

Write-Log "pushed $ahead commit(s) to origin/$branch"
exit 0