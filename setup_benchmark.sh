#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
source_dir="$root/.benchmark_src/llmperf"
revision='f1d6bed47e4501b0e371082b41601b59ab55269f'
client_file="$root/vendor/llmperf_openai_client.py"

if [[ ! -d "$source_dir/.git" ]]; then
    mkdir -p "$root/.benchmark_src"
    git clone --depth 1 https://github.com/ray-project/llmperf.git "$source_dir"
fi

git_safe=(git -c "safe.directory=$source_dir" -C "$source_dir")
if ! "${git_safe[@]}" cat-file -e "${revision}^{commit}" 2>/dev/null; then
    "${git_safe[@]}" fetch --depth 1 origin "$revision"
fi
"${git_safe[@]}" checkout --detach "$revision"
cp -- "$client_file" "$source_dir/src/llmperf/ray_clients/openai_chat_completions_client.py"

venv_dir="$root/.venv-linux"
if [[ ! -x "$venv_dir/bin/python" ]]; then
    python3 -m venv "$venv_dir"
fi
"$venv_dir/bin/python" -m pip install -r "$root/requirements.txt"
printf '%s\n' 'LLMPerf benchmark environment ready.'
