<#
.SYNOPSIS
Creates the local TrustExtract virtual environment and installs dependencies.

.EXAMPLE
.\scripts\setup_env.ps1

.EXAMPLE
.\scripts\setup_env.ps1 -PythonExecutable "C:\Python314\python.exe"
#>

[CmdletBinding()]
param(
    [string]$PythonExecutable = "py"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$launcherArguments = if ($PythonExecutable -eq "py") { @("-3") } else { @() }

Push-Location $projectRoot
try {
    & $PythonExecutable @launcherArguments --version
    if ($LASTEXITCODE -ne 0) {
        throw "Python exited with code $LASTEXITCODE."
    }

    if (-not (Test-Path $venvPython)) {
        & $PythonExecutable @launcherArguments -m venv .venv
        if ($LASTEXITCODE -ne 0) {
            throw "Virtual environment creation failed with code $LASTEXITCODE."
        }
    }

    & $venvPython -m pip install --upgrade pip
    & $venvPython -m pip install -e ".[dev]"

    Write-Host "`nEnvironment is ready. Activate it with:"
    Write-Host ".\.venv\Scripts\Activate.ps1"
}
finally {
    Pop-Location
}
