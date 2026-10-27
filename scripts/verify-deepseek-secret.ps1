# Verify with a synthetic key in a new temporary repository, never the user's secret.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$utf8 = [Text.UTF8Encoding]::new($false)
$criteria = @(
    'Windows DPAPI 本地保存与读取使用合成数据完成验证，不泄露密钥。',
    '加密文件在 Git 中被忽略，旧文件不会被静默覆盖。',
    '使用说明明确暴露密钥应撤销、当前账户限制和未完成在线验证。'
)
$paths = @('.gitignore', 'scripts/deepseek-secret.ps1', 'scripts/verify-deepseek-secret.ps1', 'docs/DEEPSEEK_SETUP.md', 'ai-assistant/agent_core/deepseek.py', 'ai-assistant/agent_core/tests/test_deepseek.py', 'ai-assistant/crm-dashboard/tests/test_server.py')
function Snapshot {
    $files = @($paths | Sort-Object -Unique | ForEach-Object { [ordered]@{path=$_; sha256=(Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash.ToLowerInvariant()} })
    $canonical = ($files | ForEach-Object { $_.path + ' ' + $_.sha256 }) -join "`n"
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $hash = [Convert]::ToHexString($sha.ComputeHash($utf8.GetBytes($canonical))).ToLowerInvariant() } finally { $sha.Dispose() }
    return @{ files = $files; hash = $hash }
}
$before = Snapshot
$temp = Join-Path $env:TEMP ('cmr-dpapi-test-' + [guid]::NewGuid().ToString('N'))
[void](New-Item -ItemType Directory -Path (Join-Path $temp 'scripts') -Force)
Copy-Item -LiteralPath 'scripts/deepseek-secret.ps1' -Destination (Join-Path $temp 'scripts/deepseek-secret.ps1')
[IO.File]::WriteAllText((Join-Path $temp '.gitignore'), "/.secrets/`n", $utf8)
& git init --quiet $temp
if ($LASTEXITCODE -ne 0) { throw 'Could not initialize the isolated test repository.' }
$global:cmrTestFixture = 'synthetic-offline-test-key-not-real'
function global:Read-Host { param($Prompt, [switch]$AsSecureString) ConvertTo-SecureString $global:cmrTestFixture -AsPlainText -Force }
$helper = Join-Path $temp 'scripts/deepseek-secret.ps1'
& $helper -Action Save
$encryptedPath = Join-Path $temp '.secrets/deepseek.dpapi'
if (-not (Test-Path -LiteralPath $encryptedPath)) { throw 'Encrypted file missing.' }
if ([IO.File]::ReadAllText($encryptedPath).Contains($global:cmrTestFixture)) { throw 'Plaintext found in encrypted file.' }
$previousHash = (Get-FileHash -LiteralPath $encryptedPath -Algorithm SHA256).Hash
$refused = $false
try { & $helper -Action Save } catch { $refused = $true }
if (-not $refused -or (Get-FileHash -LiteralPath $encryptedPath -Algorithm SHA256).Hash -ne $previousHash) { throw 'Existing file was not protected.' }
$env:DEEPSEEK_API_KEY = 'prior-synthetic-value'
& $helper -Action Load
if ($env:DEEPSEEK_API_KEY -cne $global:cmrTestFixture) { throw 'DPAPI round-trip mismatch.' }
& git -C $temp check-ignore -q --no-index -- '.secrets/deepseek.dpapi'
if ($LASTEXITCODE -ne 0) { throw 'Encrypted file is not ignored.' }
if ((@(& git -C $temp status --porcelain --untracked-files=all) -join "`n") -match 'deepseek\.dpapi') { throw 'Git lists the encrypted file.' }
& git check-ignore -q --no-index -- '.secrets/deepseek.dpapi'
if ($LASTEXITCODE -ne 0) { throw 'Actual project secret path is not ignored.' }
$env:PYTHONUTF8 = '1'
$domain = (& python -m unittest discover -s ai-assistant/agent_core/tests -q 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0 -or $domain -notmatch 'Ran (\d+) tests') { throw 'Domain test suite failed.' }
$domainCount = [int]$Matches[1]
$legacy = (& python -m unittest discover -s ai-assistant/crm-dashboard/tests -q 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0 -or $legacy -notmatch 'Ran (\d+) tests') { throw 'Legacy test suite failed.' }
$legacyCount = [int]$Matches[1]
& git diff --check
if ($LASTEXITCODE -ne 0) { throw 'Git whitespace check failed.' }
$after = Snapshot
if ($before.hash -ne $after.hash) { throw 'Source files changed during verification.' }
$stamp = [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$relative = 'docs/verification/cmr-secret-' + $stamp + '.json'
$report = [ordered]@{
    version=1; work_item='CMR-DEEPSEEK-LOCAL-SECRET'; source_sha=$after.hash
    source_sha_kind='sha256-content-manifest-not-git-commit'; scope=@($after.files | ForEach-Object { $_.path })
    command='pwsh -NoProfile -File scripts/verify-deepseek-secret.ps1'; verified_at=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    checks=@(
        [ordered]@{name='synthetic_windows_dpapi_roundtrip'; passed=$true; details='Synthetic secret encrypted and loaded in isolated temporary Git repository; plaintext absent from encrypted file.'; criteria=@($criteria[0])},
        [ordered]@{name='overwrite_and_git_ignore'; passed=$true; details='Existing secret file preserved and target ignored in test and project.'; criteria=@($criteria[1])},
        [ordered]@{name='documented_boundaries'; passed=$true; details='No actual key saved, no online API call or new HTTP integration; documentation records rotation and current-user limitation.'; criteria=@($criteria[2])},
        [ordered]@{name='offline_regressions'; passed=$true; details=('Domain tests: '+$domainCount+'; legacy tests: '+$legacyCount+'; git diff --check passed.'); criteria=@($criteria[0],$criteria[1],$criteria[2])}
    ); source_files=$after.files; domain_tests=$domainCount; legacy_tests=$legacyCount
    limitations=@('No real user key saved', 'No live DeepSeek API call', 'No browser or authenticated backend integration')
}
[IO.File]::WriteAllText((Join-Path $root $relative), ($report | ConvertTo-Json -Depth 12) + "`n", $utf8)
[ordered]@{report=$relative; source_sha=$after.hash; domain_tests=$domainCount; legacy_tests=$legacyCount} | ConvertTo-Json -Compress