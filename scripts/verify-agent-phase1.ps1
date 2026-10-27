param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
Set-Location -LiteralPath $ProjectRoot
$env:PYTHONUTF8 = '1'
$utf8 = [Text.UTF8Encoding]::new($false)
$criteria = @(
    'P1-C1: Scoped customer read tools and pricing/policy boundary tests pass.',
    'P1-C2: Existing CRM regression, Python compilation and JavaScript syntax checks pass.',
    'P1-C3: Delivery scope, immutable source snapshot and unchanged legacy entry points are recorded.'
)

function Read-SourceSnapshot {
    $paths = @(Get-ChildItem -LiteralPath 'ai-assistant/agent_core' -Recurse -File |
        Where-Object { $_.Extension -in @('.py', '.md') } |
        ForEach-Object { [IO.Path]::GetRelativePath($ProjectRoot, $_.FullName).Replace('\', '/') })
    $paths += @(
        'ai-assistant/crm-dashboard/server.py',
        'ai-assistant/crm-dashboard/app.js',
        'ai-assistant/crm-dashboard/index.html',
        'ai-assistant/crm-dashboard/styles.css',
        'ai-assistant/crm-dashboard/tests/test_server.py',
        'docs/superpowers/specs/2026-10-26-agent-workbench-plan.md',
        'scripts/verify-agent-phase1.ps1'
    )
    $files = @($paths | Sort-Object -Unique | ForEach-Object {
        $file = Get-Item -LiteralPath $_
        [ordered]@{
            path = $_
            sha256 = (Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash.ToLowerInvariant()
            bytes = $file.Length
        }
    })
    $canonical = ($files | ForEach-Object { $_.path + ' ' + $_.sha256 }) -join "`n"
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $hash = [Convert]::ToHexString($sha.ComputeHash($utf8.GetBytes($canonical))).ToLowerInvariant() }
    finally { $sha.Dispose() }
    return @{ files = $files; hash = $hash }
}

function Invoke-Check([string]$Name, [string]$Executable, [string[]]$Arguments, [string[]]$Covers) {
    $output = (& $Executable @Arguments 2>&1 | Out-String).Trim()
    $code = $LASTEXITCODE
    [ordered]@{
        name = $Name
        passed = ($code -eq 0)
        details = if ($output) { $output } else { 'Process exited with code ' + $code }
        command = $Executable + ' ' + ($Arguments -join ' ')
        exit_code = $code
        criteria = $Covers
    }
}

$before = Read-SourceSnapshot
$checks = @(
    (Invoke-Check 'domain_tests' 'python' @('-m', 'unittest', 'discover', '-s', 'ai-assistant/agent_core/tests', '-q') @($criteria[0])),
    (Invoke-Check 'legacy_tests' 'python' @('-m', 'unittest', 'discover', '-s', 'ai-assistant/crm-dashboard/tests', '-q') @($criteria[1])),
    (Invoke-Check 'python_compile' 'python' @('-m', 'compileall', '-q', 'ai-assistant/agent_core') @($criteria[1])),
    (Invoke-Check 'javascript_syntax' 'node' @('--check', 'ai-assistant/crm-dashboard/app.js') @($criteria[1])),
    (Invoke-Check 'git_diff_check' 'git' @('diff', '--check') @($criteria[1])),
    (Invoke-Check 'legacy_entrypoints_unchanged' 'git' @('diff', '--exit-code', 'HEAD', '--', 'ai-assistant/crm-dashboard/server.py', 'ai-assistant/crm-dashboard/app.js', 'ai-assistant/crm-dashboard/index.html', 'ai-assistant/crm-dashboard/styles.css', 'ai-assistant/crm-dashboard/tests/test_server.py') @($criteria[2]))
)
$after = Read-SourceSnapshot
if ($before.hash -ne $after.hash) { throw 'Source files changed during verification; do not register completion.' }
foreach ($check in $checks) { if (-not $check.passed) { throw ($check.name + ' failed: ' + $check.details) } }
if ($checks[0].details -notmatch 'Ran (\d+) tests' -or [int]$Matches[1] -lt 52) { throw 'Domain test count not verified.' }
$domainCount = [int]$Matches[1]
if ($checks[1].details -notmatch 'Ran (\d+) tests' -or [int]$Matches[1] -lt 44) { throw 'Legacy test count not verified.' }
$legacyCount = [int]$Matches[1]
$checks += [ordered]@{
    name = 'scope_and_source_snapshot'
    passed = $true
    details = 'Content-hash snapshot unchanged during checks. No new HTTP service or UI was started; authentication, PostgreSQL, model calls, Wiki/RAG and production migration are outside this completion.'
    criteria = @($criteria[2])
}
$directory = Join-Path $ProjectRoot '.awr/reports'
[IO.Directory]::CreateDirectory($directory) | Out-Null
$stamp = [DateTimeOffset]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$relative = '.awr/reports/cmr-phase1-' + $stamp + '.json'
$report = [ordered]@{
    version = 1
    work_item = 'CMR-P1-RULES'
    source_sha = $after.hash
    source_sha_kind = 'sha256-content-manifest-not-git-commit'
    command = 'pwsh -NoProfile -File scripts/verify-agent-phase1.ps1'
    scope = @($after.files | ForEach-Object { $_.path })
    verified_at = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    checks = $checks
    source_files = $after.files
    git_head = (& git rev-parse HEAD).Trim()
    git_working_tree_dirty = $true
    domain_tests = $domainCount
    legacy_tests = $legacyCount
    limitations = @('No new HTTP/UI integration', 'No authentication/database integration', 'No real LLM or Wiki/RAG', 'No production data migration', 'No new browser acceptance')
}
[IO.File]::WriteAllText((Join-Path $ProjectRoot $relative), ($report | ConvertTo-Json -Depth 10) + "`n", $utf8)
[ordered]@{ report = $relative; source_sha = $after.hash; domain_tests = $domainCount; legacy_tests = $legacyCount; verified_at = $report.verified_at } | ConvertTo-Json -Compress
