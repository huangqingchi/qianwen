# API 接口性能测试

本项目现在使用 [LLMPerf](https://github.com/ray-project/llmperf) 的 Ray 并发客户端，测量百炼 API 和 OpenAI 兼容本地接口的客户端体验。旧的七项自写评测已移除。`qwen_chat.py` 仍可用于手工聊天。

## 安装独立环境

Windows PowerShell：

```powershell
cd Z:\qianwen
.\setup_benchmark.ps1
```

Ubuntu Bash：

```bash
cd /path/to/qianwen
bash ./setup_benchmark.sh
```

脚本把指定版本的 LLMPerf 克隆到 `.benchmark_src/llmperf`，将 `vendor/llmperf_openai_client.py` 安装为项目使用的 OpenAI 兼容客户端，并安装 `requirements.txt` 中的最小依赖。Windows 使用 `.venv`，Ubuntu 使用独立的 `.venv-linux`，避免在跨系统共享目录时混用虚拟环境。Ubuntu 需要系统提供 Python 3 和 `venv` 模块。此处用 LLMPerf 的 Ray 客户端执行并发请求；客户端适配流式完成判定、usage 与推理文本的时间记录，并避免把响应正文或密钥写入结果。上游版本声明 Python 3.8–3.10；本项目通过最小依赖和客户端适配在本机 Windows Python 3.12 环境运行，未使用其旧的 `token_benchmark_ray.py` 命令行脚本。

## 运行

把百炼 API Key 放在根目录 `本地密钥.txt`（单独一行），或设置 `DASHSCOPE_API_KEY`。密钥文件和结果目录都被 Git 忽略。默认模型为 `glm-5.3`，默认接口地址为 `https://dashscope.aliyuncs.com/compatible-mode/v1`。

```powershell
# 极小规模兼容性测试：1 次预热 + 1 次采集
.\.venv\Scripts\python.exe .\benchmark.py --endpoint api --profile smoke

# 先看请求计划，不调用 API
.\.venv\Scripts\python.exe .\benchmark.py --profile standard --dry-run

# 默认只测短输入、固定并发 4：100 次采集 + 4 次预热
.\.venv\Scripts\python.exe .\benchmark.py --endpoint api --profile standard

# 本地 OpenAI 兼容接口使用相同负载；地址填到 /v1，不能包含 /chat/completions
.\.venv\Scripts\python.exe .\benchmark.py --endpoint local --base-url http://127.0.0.1:8000/v1 --model YOUR_MODEL --profile standard
```

Ubuntu 对应命令：

```bash
.venv-linux/bin/python benchmark.py --profile standard --dry-run
.venv-linux/bin/python benchmark.py --endpoint api --profile standard
.venv-linux/bin/python benchmark.py --endpoint local --base-url http://127.0.0.1:8000/v1 --model YOUR_MODEL --profile standard
```

本地接口若需鉴权，设置 `LOCAL_API_KEY`；若无需鉴权，客户端发送占位 Bearer 值。正式测试前确认本地模型、请求限额和输出长度。`--output-dir` 可设置结果目录，默认位于 `benchmark_results/<时间>/`。

每轮生成逐请求 JSONL、`summary.json`、`summary.csv`、`metadata.json` 和图表式 `性能报告.pdf`。字段名均为中文。`smoke` 的 PDF 展示单次请求时间线；默认的并发 4 多请求 PDF 展示 100 次请求的耗时直方图、累计分布、逐请求散点图和首生成/可见文本时间。若显式指定多个长度或并发档，PDF 再生成分场景页面。逐请求数据包括 HTTP 状态、E2E、首生成事件、首段可见文字、SSE 事件时间、服务端 usage 和错误类别；不保存提示词正文、回答正文或密钥。`benchmark_workload.json` 固定负载生成参数与随机种子，每条记录带提示词 SHA256，汇总记录整轮提示词集合的校验值。已有英文结果可用 `python localize_results.py benchmark_results/<运行时间>` 转换，对比脚本也兼容旧英文结果。

已有结果可以直接补生成 PDF，无需再次调用模型：

```powershell
.\.venv\Scripts\python.exe .\pdf_report.py benchmark_results\<运行时间>
```

Ubuntu 使用 `.venv-linux/bin/python pdf_report.py benchmark_results/<运行时间>`。PDF 会尝试系统中文字体；如本机需要指定字体，可设置 `QIANWEN_PDF_FONT` 为已有 `.ttf` 字体的绝对路径。

`standard` 默认固定并发 **4**、短输入、采集 **100** 条并预热 **4** 条。这能查看并发 4 下的请求分布；一轮结果不代表长期稳定性。执行前用 `--dry-run` 核对总量。可通过 `--requests-per-run`、`--scenarios`、`--concurrencies`、`--repeats`、`--warmup-rounds` 明确扩展，例如 `--scenarios short,medium,long --repeats 3`；长输入会明显增加运行时间和用量。需要记录环境信息时可传入 `--client-location` 和 `--service-region`。两端运行完成后生成并排表：

```powershell
.\.venv\Scripts\python.exe .\compare_benchmark.py benchmark_results\API_RUN\summary.json benchmark_results\LOCAL_RUN\summary.json --output benchmark_results\comparison.md
```

## 结果口径

- 成功要求 HTTP 200、可见正文非空，且流收到 `[DONE]`。失败请求进入错误率分母，不进入延迟分位数。
- `服务端输出token每秒` 使用服务端 `usage.completion_tokens`，推理模型可能把推理 token 算入其中；它不是可见文字生成速度。缺少 usage 时该项为空。
- 默认 `glm-5.3` 必须以思考模式运行；负载文件将 `reasoning_effort` 设为 `low`，使合成负载能在输出上限内完成。`max_tokens` 包含推理 token。若流式 `finish_reason=length`，即使有正文，也将该请求记为截断失败。本地模型不支持该参数时，应修改负载文件，并用同一版本重新测两端。
- “首生成事件”可来自 `reasoning_content`；它不一定是严格的首 token 时间。一次 SSE 事件也不一定对应一个 token，因此不报告伪造的 token 间隔或 TPOT。
- `smoke` 只验证接口兼容性。双端比较需两端使用同一个 `benchmark_workload.json`，从同一客户端按相同并发和请求数运行，逐档检查实际输入/输出长度、模型配置、缓存和限流。不同模型的结果应标为两套服务的使用体验比较。
- 单轮成功样本少于 100 条时不计算 p95；更大样本的 p95 仍需结合多轮结果判断稳定性。当前负载模式为固定并发，不能直接解释为固定到达率下的表现。

完整的测量口径见 [API 接口性能对比方案](API接口性能对比方案.md)。
