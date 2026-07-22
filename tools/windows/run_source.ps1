param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Branch = "test-live-sync"
Set-Location -LiteralPath $Repo

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )

    & $FilePath @Arguments
    $ExitCode = $LASTEXITCODE
    if ($ExitCode -ne 0) {
        throw "Command failed with exit code ${ExitCode}: $FilePath $($Arguments -join ' ')"
    }
}

function Git-Output {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $Output = & git @Arguments
    $ExitCode = $LASTEXITCODE
    if ($ExitCode -ne 0) {
        throw "Git command failed with exit code ${ExitCode}: git $($Arguments -join ' ')"
    }
    return (($Output | Out-String).Trim())
}

function Assert-Synchronized {
    param([string]$Stage)

    $Status = Git-Output -Arguments @(
        "status", "--porcelain=v1", "--untracked-files=all"
    )
    if ($Status) {
        Write-Host $Status -ForegroundColor Yellow
        throw "$Stage failed: the repository contains modified, staged, or untracked files."
    }

    $LocalHead = Git-Output -Arguments @("rev-parse", "HEAD")
    $RemoteHead = Git-Output -Arguments @("rev-parse", "origin/$Branch")
    if ($LocalHead -ne $RemoteHead) {
        $Counts = Git-Output -Arguments @(
            "rev-list", "--left-right", "--count", "origin/$Branch...HEAD"
        )
        throw "$Stage failed: local HEAD does not match origin/$Branch. Distance: $Counts"
    }
}

$CurrentBranch = Git-Output -Arguments @("branch", "--show-current")
if ($CurrentBranch -ne $Branch) {
    throw "Source runs are restricted to $Branch. Current branch: $CurrentBranch"
}

$Remote = Git-Output -Arguments @("remote", "get-url", "origin")
$NormalizedRemote = $Remote.Trim().TrimEnd("/").ToLowerInvariant()
if ($NormalizedRemote.EndsWith(".git")) {
    $NormalizedRemote = $NormalizedRemote.Substring(0, $NormalizedRemote.Length - 4)
}
if ($NormalizedRemote -notmatch "github\.com[:/]+gspeq/rust-comp$") {
    throw "origin is '$Remote', not Gspeq/Rust-Comp."
}

Write-Host ""
Write-Host "[1/6] Verifying local and remote synchronization..." -ForegroundColor Cyan
Invoke-Checked -FilePath "git" -Arguments @(
    "fetch", "--prune", "origin", $Branch
)
Assert-Synchronized -Stage "Initial synchronization"

$Python = Join-Path $Repo ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    Write-Host "[2/6] Creating the source virtual environment..." -ForegroundColor Cyan
    $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $PyLauncher) {
        Invoke-Checked -FilePath $PyLauncher.Source -Arguments @(
            "-3", "-m", "venv", ".venv"
        )
    }
    else {
        $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if ($null -eq $PythonCommand) {
            throw "Python 3 was not found."
        }
        Invoke-Checked -FilePath $PythonCommand.Source -Arguments @(
            "-m", "venv", ".venv"
        )
    }
}
else {
    Write-Host "[2/6] Source virtual environment found." -ForegroundColor Cyan
}

$env:PIP_NO_CACHE_DIR = "1"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$env:RUST_COMPANION_HIDE_CONSOLE_AFTER_GUI = "1"
$env:PYTHONUNBUFFERED = "1"

Write-Host "[3/6] Verifying source dependencies..." -ForegroundColor Cyan
Invoke-Checked -FilePath $Python -Arguments @(
    "-m", "pip", "install", "--no-cache-dir", "-r", "requirements.txt"
)

Write-Host "[4/6] Compiling and testing every source module..." -ForegroundColor Cyan
Invoke-Checked -FilePath $Python -Arguments @(
    "-m", "compileall", "-q", "launcher.py", "main.py", "rust_companion_plus"
)
# unittest discover
Invoke-Checked -FilePath $Python -Arguments @(
    "-m", "unittest", "discover", "-s", "tests", "-v"
)
# git diff --check
Invoke-Checked -FilePath "git" -Arguments @("diff", "--check")

Write-Host "[5/6] Rechecking synchronization after tests..." -ForegroundColor Cyan
Invoke-Checked -FilePath "git" -Arguments @(
    "fetch", "--prune", "origin", $Branch
)
Assert-Synchronized -Stage "Post-test synchronization"

Write-Host "[6/6] All tests passed. Starting Rust Companion+..." -ForegroundColor Green
& $Python (Join-Path $Repo "main.py")
exit $LASTEXITCODE
