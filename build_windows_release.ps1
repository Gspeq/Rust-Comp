param(
    [string]$Version = "",
    [switch]$InstallAfterBuild,
    [switch]$SkipTests
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Step([string]$Text) {
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Fail([string]$Text) {
    Write-Host ""
    Write-Host "BUILD FAILED: $Text" -ForegroundColor Red
    exit 1
}

$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Repo

if ($env:OS -ne "Windows_NT") {
    Fail "Rust Companion+ Windows releases must be built on Windows."
}

$VersionFile = Join-Path $Repo "rust_companion_plus\version.py"
if (-not $Version) {
    if (-not (Test-Path $VersionFile)) {
        Fail "Missing version file: $VersionFile"
    }
    $VersionText = Get-Content $VersionFile -Raw
    $Match = [regex]::Match(
        $VersionText,
        '__version__\s*=\s*"([^"]+)"'
    )
    if (-not $Match.Success) {
        Fail "Could not read __version__ from version.py."
    }
    $Version = $Match.Groups[1].Value
}

if ($Version -notmatch '^\d+\.\d+\.\d+(\.\d+)?$') {
    Fail "Version must contain three or four numeric parts."
}

$BasePython = $null
if (Test-Path (Join-Path $Repo ".venv\Scripts\python.exe")) {
    $BasePython = Join-Path $Repo ".venv\Scripts\python.exe"
}
elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $BasePython = "py"
}
elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $BasePython = "python"
}
else {
    Fail "Python was not found."
}

$ReleaseVenv = Join-Path $Repo ".release-venv"
$ReleasePython = Join-Path $ReleaseVenv "Scripts\python.exe"
$BuildRoot = Join-Path $Repo ".release-build"
$DistRoot = Join-Path $Repo "release\app"
$BundleDir = Join-Path $DistRoot "RustCompanionPlus"
$InstallerOutput = Join-Path $Repo "release"
$SpecPath = Join-Path $Repo "packaging\RustCompanionPlus.spec"
$IssPath = Join-Path $Repo "packaging\RustCompanionPlus.iss"
$Entrypoint = Join-Path $Repo "main.py"
$IconPath = Join-Path $Repo "packaging\rust_companion_plus.ico"
$VersionInfoPath = Join-Path $Repo "packaging\windows_version_info.txt"

Step "Verifying release source"
$Forbidden = @(
    "run_debug_windows.bat",
    "collect_debug_bundle.bat",
    "verify_dev_build.bat",
    "remove_dev_diagnostics.ps1",
    "rust_companion_plus\debug_tools.py"
)
foreach ($Relative in $Forbidden) {
    if (Test-Path (Join-Path $Repo $Relative)) {
        Fail "Development-only file is still present: $Relative"
    }
}

if (-not (Test-Path $Entrypoint -PathType Leaf)) {
    Fail "Missing PyInstaller entrypoint: $Entrypoint"
}

$SpecText = Get-Content $SpecPath -Raw
if ($SpecText -match 'parent\.parent') {
    Fail (
        "The PyInstaller spec still resolves above the repository. " +
        "Expected packaging -> repository, not packaging -> repository -> parent."
    )
}
if (
    $SpecText -notmatch 'ROOT\s*=\s*SPEC_DIR\.parent' -or
    $SpecText -notmatch 'ENTRYPOINT\s*=\s*ROOT\s*/\s*"main\.py"'
) {
    Fail "The PyInstaller spec does not declare the verified repository entrypoint."
}

$ResolvedRepo = (Resolve-Path $Repo).Path
$ResolvedEntrypoint = (Resolve-Path $Entrypoint).Path
$EntrypointParent = Split-Path -Parent $ResolvedEntrypoint
if ($EntrypointParent -ne $ResolvedRepo) {
    Fail (
        "Resolved entrypoint is outside the repository: " +
        $ResolvedEntrypoint
    )
}
Write-Host "PyInstaller repository: $ResolvedRepo"
Write-Host "PyInstaller entrypoint: $ResolvedEntrypoint"

Step "Creating isolated release environment"
if (-not (Test-Path $ReleasePython)) {
    & $BasePython -m venv $ReleaseVenv
    if ($LASTEXITCODE -ne 0) {
        Fail "Could not create .release-venv."
    }
}

& $ReleasePython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    Fail "pip upgrade failed."
}
& $ReleasePython -m pip install `
    --requirement (Join-Path $Repo "requirements.txt") `
    --requirement (Join-Path $Repo "requirements-build.txt")
if ($LASTEXITCODE -ne 0) {
    Fail "Release dependencies failed to install."
}

if (-not $SkipTests) {
    Step "Running source tests"
    & $ReleasePython -m unittest discover `
        -s (Join-Path $Repo "tests") -v
    if ($LASTEXITCODE -ne 0) {
        Fail "Source test suite failed."
    }
}

Step "Generating Windows icon and version resources"
& $ReleasePython `
    (Join-Path $Repo "packaging\generate_windows_assets.py") `
    --version $Version `
    --icon $IconPath `
    --version-file $VersionInfoPath
if ($LASTEXITCODE -ne 0) {
    Fail "Windows resource generation failed."
}

Step "Cleaning previous release output"
Remove-Item $BuildRoot -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $DistRoot -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $BuildRoot -Force | Out-Null
New-Item -ItemType Directory -Path $DistRoot -Force | Out-Null
New-Item -ItemType Directory -Path $InstallerOutput -Force | Out-Null

Step "Building the Windows application"
& $ReleasePython -m PyInstaller `
    --noconfirm `
    --clean `
    --workpath $BuildRoot `
    --distpath $DistRoot `
    $SpecPath
if ($LASTEXITCODE -ne 0) {
    Fail "PyInstaller build failed."
}

$BuiltExe = Join-Path $BundleDir "RustCompanionPlus.exe"
if (-not (Test-Path $BuiltExe)) {
    Fail "Expected executable was not created: $BuiltExe"
}

Step "Writing source-only build manifest"
$TrackedSourceRoots = @(
    (Join-Path $Repo "rust_companion_plus"),
    (Join-Path $Repo "main.py"),
    (Join-Path $Repo "requirements.txt"),
    (Join-Path $Repo "requirements-build.txt"),
    (Join-Path $Repo "packaging")
)
$ManifestFiles = @()
foreach ($Root in $TrackedSourceRoots) {
    if (Test-Path $Root -PathType Leaf) {
        $Items = @(Get-Item $Root)
    }
    elseif (Test-Path $Root -PathType Container) {
        $Items = @(Get-ChildItem $Root -File -Recurse)
    }
    else {
        continue
    }

    foreach ($Item in $Items) {
        if ($Item.Extension -in @(".pyc", ".pyo")) {
            continue
        }
        $ManifestFiles += [ordered]@{
            path = $Item.FullName.Substring($Repo.Length + 1)
            sha256 = (Get-FileHash $Item.FullName -Algorithm SHA256).Hash
            size = $Item.Length
        }
    }
}

$GitCommit = ""
if (Get-Command git -ErrorAction SilentlyContinue) {
    $GitCommit = (& git rev-parse HEAD 2>$null).Trim()
}

$Manifest = [ordered]@{
    application = "Rust Companion+"
    version = $Version
    built_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    source_repository = $Repo
    git_commit = $GitCommit
    source_files = $ManifestFiles
}
$ManifestPath = Join-Path $BundleDir "build-manifest.json"
[System.IO.File]::WriteAllText(
    $ManifestPath,
    ($Manifest | ConvertTo-Json -Depth 6),
    [System.Text.UTF8Encoding]::new($false)
)

Step "Running packaged executable self-test"
& $BuiltExe --self-test
if ($LASTEXITCODE -ne 0) {
    Fail "Packaged executable self-test failed."
}

function Find-InnoCompiler {
    $Candidates = @(
        (Join-Path $env:ProgramFiles "Inno Setup 7\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 7\ISCC.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 7\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
    )
    foreach ($Candidate in $Candidates) {
        if ($Candidate -and (Test-Path $Candidate)) {
            return $Candidate
        }
    }
    return $null
}

Step "Locating the Windows installer compiler"
$Iscc = Find-InnoCompiler
if (-not $Iscc) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Fail (
            "Inno Setup was not found and winget is unavailable. " +
            "Install Inno Setup 7, then run this builder again."
        )
    }

    $Answer = Read-Host (
        "Inno Setup is required to create the installer. " +
        "Install it through winget now? [Y/n]"
    )
    if ($Answer -match '^(?i)n(o)?$') {
        Fail "Installer build cancelled because Inno Setup is missing."
    }

    & winget install `
        --id JRSoftware.InnoSetup.7 `
        --exact `
        --source winget `
        --silent `
        --accept-package-agreements `
        --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        Fail "winget could not install Inno Setup."
    }

    $Iscc = Find-InnoCompiler
    if (-not $Iscc) {
        Fail "Inno Setup installed, but ISCC.exe could not be located."
    }
}

Step "Compiling the Windows installer"
& $Iscc `
    "/DMyAppVersion=$Version" `
    "/DSourceDir=$BundleDir" `
    "/DOutputDir=$InstallerOutput" `
    $IssPath
if ($LASTEXITCODE -ne 0) {
    Fail "Inno Setup compilation failed."
}

$Installer = Join-Path `
    $InstallerOutput `
    "RustCompanionPlus-Setup-$Version.exe"
if (-not (Test-Path $Installer)) {
    Fail "Expected installer was not created: $Installer"
}

$Hash = (Get-FileHash $Installer -Algorithm SHA256).Hash
Write-Host ""
Write-Host "WINDOWS RELEASE READY" -ForegroundColor Green
Write-Host "Application: $BuiltExe"
Write-Host "Installer:   $Installer"
Write-Host "SHA256:      $Hash"

if ($InstallAfterBuild) {
    Start-Process -FilePath $Installer
}
else {
    $Install = Read-Host "Run the installer now? [y/N]"
    if ($Install -match '^(?i)y(es)?$') {
        Start-Process -FilePath $Installer
    }
}
