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

# git.exe and its credential helper are console programs. -WindowStyle Hidden only
# hides THIS script's own console, not the ones Windows creates for its children, so
# starting them through & flashes a window on the desktop. CreateNoWindow stops that.
function Invoke-Git {
    param([string[]]$Arguments)
    $quoted = @($Arguments | ForEach-Object { '"' + ($_ -replace '"', '\"') + '"' }) -join ' '
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "git"
    if ($quoted) { $psi.Arguments = $quoted }
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $proc = [System.Diagnostics.Process]::Start($psi)
    $stdout = $proc.StandardOutput.ReadToEnd()
    $proc.StandardError.ReadToEnd() | Out-Null
    $proc.WaitForExit()
    $global:LASTEXITCODE = $proc.ExitCode
    if (-not $stdout) { return @() }
    return @($stdout -split "`r?`n" | Where-Object { $_ -ne "" })
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
$branch = Invoke-Git @("-C", $repoRoot, "symbolic-ref", "--short", "-q", "HEAD")
if (-not $branch) {
    Fail "detached HEAD, cannot push"
}

# 1) Snapshot local changes. Ignored files (build output, __pycache__, ...) are skipped.
$status = Invoke-Git @("-C", $repoRoot, "status", "--porcelain")
if ($status) {
    Invoke-Git @("-C", $repoRoot, "add", "-A") | Out-Null
    $staged = Invoke-Git @("-C", $repoRoot, "diff", "--cached", "--name-only")
    if ($staged) {
        $stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
        Invoke-Git @("-C", $repoRoot, "commit", "-m", "auto snapshot: $stamp") | Out-Null
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
$hasRemote = Invoke-Git @("-C", $repoRoot, "rev-parse", "--verify", "--quiet", "origin/$branch")
$ahead = 0
if ($hasRemote) {
    $cnt = Invoke-Git @("-C", $repoRoot, "rev-list", "--count", "origin/$branch..HEAD")
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

Invoke-Git @("-C", $repoRoot, "push", "origin", $branch) | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Log "push rejected, retrying after pull --rebase --autostash"
    Invoke-Git @("-C", $repoRoot, "pull", "--rebase", "--autostash", "origin", $branch) | Out-Null
    Invoke-Git @("-C", $repoRoot, "push", "origin", $branch) | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Fail "git push failed; $ahead commit(s) stay local and will be retried tomorrow"
    }
}

Write-Log "pushed $ahead commit(s) to origin/$branch"
exit 0