# ──────────────────────────────────────────────────────────────────────
# Rikugan — universal installer (Windows)
#
#   irm https://raw.githubusercontent.com/buzzer-re/Rikugan/main/install.ps1 | iex
#
# Or with arguments:
#   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/buzzer-re/Rikugan/main/install.ps1))) -Target ida
#   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/buzzer-re/Rikugan/main/install.ps1))) -Target binja
#   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/buzzer-re/Rikugan/main/install.ps1))) -Target both
#
# Environment variables:
#   RIKUGAN_DIR     — where to clone the repo   (default: ~\.rikugan)
#   RIKUGAN_BRANCH  — git branch to check out   (default: main)
#   IDA_PYTHON      — override Python for IDA    (forwarded to install_ida.bat)
#   BN_PYTHON       — override Python for BN     (forwarded to install_binaryninja.bat)
# ──────────────────────────────────────────────────────────────────────

param(
    [ValidateSet("ida", "binja", "both", "")]
    [string]$Target = ""
)

$ErrorActionPreference = "Stop"

$RepoUrl = "https://github.com/buzzer-re/Rikugan.git"
$InstallDir = if ($env:RIKUGAN_DIR) { $env:RIKUGAN_DIR } else { Join-Path $HOME ".rikugan" }
$Branch = if ($env:RIKUGAN_BRANCH) { $env:RIKUGAN_BRANCH } else { "main" }

# ── Helpers ──────────────────────────────────────────────────────────
function Write-Info    { param($Msg) Write-Host "[*] $Msg" -ForegroundColor Cyan }
function Write-Ok      { param($Msg) Write-Host "[+] $Msg" -ForegroundColor Green }
function Write-Warn    { param($Msg) Write-Host "[!] $Msg" -ForegroundColor Yellow }
function Write-Err     { param($Msg) Write-Host "[-] $Msg" -ForegroundColor Red }

function Show-Banner {
    Write-Host ""
    Write-Host "    +==========================================+" -ForegroundColor White
    Write-Host "    |            六眼  Rikugan                 |" -ForegroundColor White
    Write-Host "    |     Reverse Engineering AI Agent         |" -ForegroundColor White
    Write-Host "    |        IDA Pro  .  Binary Ninja          |" -ForegroundColor White
    Write-Host "    +==========================================+" -ForegroundColor White
    Write-Host ""
}

# ── Detection ────────────────────────────────────────────────────────
function Test-IDA {
    # Registry
    $regPaths = @(
        "HKCU:\Software\Hex-Rays\IDA",
        "HKLM:\SOFTWARE\Hex-Rays\IDA"
    )
    foreach ($rp in $regPaths) {
        if (Test-Path $rp) { return $true }
    }
    # AppData user dir
    $idaDir = Join-Path $env:APPDATA "Hex-Rays\IDA Pro"
    if (Test-Path $idaDir) { return $true }
    # USERPROFILE\.idapro
    $idapro = Join-Path $HOME ".idapro"
    if (Test-Path $idapro) { return $true }
    # IDA in PATH
    if (Get-Command "ida64.exe" -ErrorAction SilentlyContinue) { return $true }
    if (Get-Command "idat64.exe" -ErrorAction SilentlyContinue) { return $true }
    return $false
}

function Test-BinaryNinja {
    # AppData user dir
    $bnDir = Join-Path $env:APPDATA "Binary Ninja"
    if (Test-Path $bnDir) { return $true }
    # Common install locations
    $installPaths = @(
        "${env:ProgramFiles}\Vector35\BinaryNinja",
        "${env:ProgramFiles(x86)}\Vector35\BinaryNinja",
        "${env:LOCALAPPDATA}\Vector35\BinaryNinja"
    )
    foreach ($p in $installPaths) {
        if (Test-Path $p) { return $true }
    }
    return $false
}

# ── Prerequisites ────────────────────────────────────────────────────
function Test-Prerequisites {
    if (-not (Get-Command "git" -ErrorAction SilentlyContinue)) {
        Write-Err "git is required but not installed."
        Write-Err "Install from: https://git-scm.com/download/win"
        Write-Err "Or: winget install Git.Git"
        exit 1
    }
}

# ── Clone or update ──────────────────────────────────────────────────
function Install-Repository {
    $gitDir = Join-Path $InstallDir ".git"
    if (Test-Path $gitDir) {
        Write-Info "Updating existing installation at $InstallDir..."
        git -C $InstallDir fetch origin $Branch --quiet 2>$null
        git -C $InstallDir checkout $Branch --quiet 2>$null
        git -C $InstallDir reset --hard "origin/$Branch" --quiet 2>$null
        Write-Ok "Updated to latest $Branch"
    }
    else {
        if (Test-Path $InstallDir) {
            $backup = "${InstallDir}.bak.$(Get-Date -Format 'yyyyMMddHHmmss')"
            Write-Warn "$InstallDir exists but is not a git repo -- backing up to $backup"
            Rename-Item $InstallDir $backup
        }
        Write-Info "Cloning Rikugan into $InstallDir..."
        git clone --branch $Branch --depth 1 $RepoUrl $InstallDir --quiet 2>$null
        Write-Ok "Cloned successfully"
    }
}

# ── Run installers ───────────────────────────────────────────────────
function Install-IDA {
    $script = Join-Path $InstallDir "install_ida.bat"
    if (-not (Test-Path $script)) {
        Write-Err "install_ida.bat not found in $InstallDir"
        return $false
    }
    Write-Info "Running IDA Pro installer..."
    Write-Host ""
    Push-Location $InstallDir
    try {
        & cmd.exe /c $script
        $success = $LASTEXITCODE -eq 0
    }
    finally { Pop-Location }
    return $success
}

function Install-BinaryNinja {
    $script = Join-Path $InstallDir "install_binaryninja.bat"
    if (-not (Test-Path $script)) {
        Write-Err "install_binaryninja.bat not found in $InstallDir"
        return $false
    }
    Write-Info "Running Binary Ninja installer..."
    Write-Host ""
    Push-Location $InstallDir
    try {
        & cmd.exe /c $script
        $success = $LASTEXITCODE -eq 0
    }
    finally { Pop-Location }
    return $success
}

# ── Main ─────────────────────────────────────────────────────────────
Show-Banner
Test-Prerequisites

# Auto-detect if no target specified
if (-not $Target) {
    $hasIda = Test-IDA
    $hasBinja = Test-BinaryNinja

    if ($hasIda -and $hasBinja) {
        $Target = "both"
        Write-Ok "Detected both IDA Pro and Binary Ninja"
    }
    elseif ($hasIda) {
        $Target = "ida"
        Write-Ok "Detected IDA Pro"
    }
    elseif ($hasBinja) {
        $Target = "binja"
        Write-Ok "Detected Binary Ninja"
    }
    else {
        Write-Warn "No IDA Pro or Binary Ninja installation detected."
        Write-Warn "Installing anyway -- defaulting to both."
        $Target = "both"
    }
}

Write-Info "Target: $Target"
Write-Info "Install directory: $InstallDir"
Write-Host ""

Install-Repository
Write-Host ""

$failed = $false

switch ($Target) {
    "ida" {
        if (-not (Install-IDA)) { $failed = $true }
    }
    "binja" {
        if (-not (Install-BinaryNinja)) { $failed = $true }
    }
    "both" {
        if (-not (Install-IDA))   { Write-Warn "IDA installation failed"; $failed = $true }
        Write-Host ""
        if (-not (Install-BinaryNinja)) { Write-Warn "Binary Ninja installation failed"; $failed = $true }
    }
}

Write-Host ""
if ($failed) {
    Write-Warn "Installation completed with errors. Check the output above."
}
else {
    Write-Ok "Rikugan installation complete!"
}
Write-Host "  Install location: $InstallDir" -ForegroundColor DarkGray
Write-Host "  To update later:  cd $InstallDir; git pull" -ForegroundColor DarkGray
Write-Host ""
