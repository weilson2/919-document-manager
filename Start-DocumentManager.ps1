param(
    [string]$DataDir,
    [switch]$Check
)

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Create the project virtual environment and install the app using the README setup commands.'
}

$launchArgs = @('-m', 'document_manager')
if ($DataDir) {
    $launchArgs += @('--data-dir', $DataDir)
}
if ($Check) {
    $launchArgs += '--check'
}

& $python @launchArgs
exit $LASTEXITCODE
