[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Save', 'Load')]
    [string]$Action
)

$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') {
    throw 'Local DPAPI storage requires Windows. Use platform secret management on other systems.'
}
$projectRoot = Split-Path -Parent $PSScriptRoot
$relativePath = '.secrets/deepseek.dpapi'
$secretDirectory = Join-Path $projectRoot '.secrets'
$secretPath = Join-Path $secretDirectory 'deepseek.dpapi'

# Refuse saving if Git ignores are missing or the target has already been tracked.
& git -C $projectRoot check-ignore -q --no-index -- $relativePath
if ($LASTEXITCODE -ne 0) { throw 'The secret path is not ignored by Git; refusing to continue.' }
$tracked = @(& git -C $projectRoot ls-files -- $relativePath)
if ($LASTEXITCODE -ne 0 -or $tracked.Count -gt 0) { throw 'The secret path is already tracked or Git is unavailable.' }

if ($Action -eq 'Save') {
    if (Test-Path -LiteralPath $secretPath) { throw 'An encrypted key already exists; it was not overwritten.' }
    if (-not (Test-Path -LiteralPath $secretDirectory)) {
        [void](New-Item -ItemType Directory -Path $secretDirectory)
    }
    $directory = Get-Item -LiteralPath $secretDirectory -Force
    if (-not $directory.PSIsContainer -or ($directory.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'The secret directory must be a normal local directory, not a link.'
    }
    $key = Read-Host 'Enter the NEW DeepSeek API key (input hidden)' -AsSecureString
    try {
        $plain = [System.Net.NetworkCredential]::new('', $key).Password
        if ($plain -notmatch '^[A-Za-z0-9_-]{16,512}$') { throw 'Invalid or masked key; nothing was saved.' }
        $ciphertext = $key | ConvertFrom-SecureString
        # CreateNew refuses to overwrite even if another process races this check.
        $stream = [IO.File]::Open($secretPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try {
            $writer = [IO.StreamWriter]::new($stream, [Text.UTF8Encoding]::new($false))
            try { $writer.Write($ciphertext) } finally { $writer.Dispose() }
        } finally { $stream.Dispose() }
        Write-Host 'Encrypted key saved locally. No key value was printed.'
    } finally {
        $plain = $null
        if ($key) { $key.Dispose() }
    }
} else {
    if (-not (Test-Path -LiteralPath $secretPath -PathType Leaf)) { throw 'No encrypted key exists. Run the Save action first.' }
    $directory = Get-Item -LiteralPath $secretDirectory -Force
    $file = Get-Item -LiteralPath $secretPath -Force
    if (($directory.Attributes -band [IO.FileAttributes]::ReparsePoint) -or ($file.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'The secret path must not be a link.'
    }
    try {
        $key = [IO.File]::ReadAllText($secretPath) | ConvertTo-SecureString
        $plain = [System.Net.NetworkCredential]::new('', $key).Password
        if ($plain -notmatch '^[A-Za-z0-9_-]{16,512}$') { throw 'Invalid secret format.' }
        $env:DEEPSEEK_API_KEY = $plain
        Write-Host 'DeepSeek key loaded into the current PowerShell process.'
    } catch {
        throw 'Unable to decrypt the local key with the current Windows account. No key was loaded.'
    } finally {
        $plain = $null
        if ($key) { $key.Dispose() }
    }
}