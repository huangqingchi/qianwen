$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $root '.benchmark_src\llmperf'
$revision = 'f1d6bed47e4501b0e371082b41601b59ab55269f'
$client = Join-Path $root 'vendor\llmperf_openai_client.py'

if (-not (Test-Path -LiteralPath (Join-Path $source '.git'))) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $source) -Force | Out-Null
    git clone --depth 1 https://github.com/ray-project/llmperf.git $source
    if ($LASTEXITCODE -ne 0) { throw 'LLMPerf clone failed' }
}
$safe = "safe.directory=$($source.Replace('\', '/'))"
git -c $safe -C $source cat-file -e "$revision^{commit}" 2>$null
if ($LASTEXITCODE -ne 0) {
    git -c $safe -C $source fetch --depth 1 origin $revision
    if ($LASTEXITCODE -ne 0) { throw 'LLMPerf revision fetch failed' }
}
git -c $safe -C $source checkout --detach $revision
if ($LASTEXITCODE -ne 0) { throw 'LLMPerf checkout failed' }
Copy-Item -LiteralPath $client -Destination (Join-Path $source 'src\llmperf\ray_clients\openai_chat_completions_client.py') -Force

$venv = Join-Path $root '.venv'
if (-not (Test-Path -LiteralPath (Join-Path $venv 'Scripts\python.exe'))) {
    python -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
}
& (Join-Path $venv 'Scripts\python.exe') -m pip install -r (Join-Path $root 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'dependency install failed' }
Write-Host 'LLMPerf benchmark environment ready.'
