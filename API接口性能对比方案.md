# 远程 API 与本地部署接口：性能对比方案

## 目标

测的是**客户端实际调用接口的效率和稳定性**，不是模型知识或答题能力。未来让同一台压测客户端向百炼 API 和本地模型接口发送同一批请求，比较在相同负载下的响应时间、吞吐和失败率。如果两端并非同一模型与配置，报告应标为“两套服务的使用体验比较”，不能把差异全部归因于部署方式。

本方案规定测量口径。当前项目已选用 LLMPerf 的 Ray 并发客户端，并完成百炼端的极小规模兼容性测试；正式双端压测仍需本地接口地址和模型信息。测试入口和环境安装见 [README](README.md)。

## 参考的开源项目

| 项目 | 可借鉴的方法 | 对本项目的边界 |
| --- | --- | --- |
| [GuideLLM](https://github.com/vllm-project/guidellm) | OpenAI 兼容 HTTP 后端、真实或合成数据、串行/并发/固定到达率/扫描负载、warmup 与 cooldown、TTFT/ITL/总时延分布，输出 JSON/CSV/HTML。 | 官方安装前提是 Linux 或 macOS；在 Windows 原生环境使用前需另行验证。对百炼地址与鉴权也要先做小样本兼容性验证。 |
| [vLLM bench serve](https://docs.vllm.ai/en/stable/cli/bench/serve/) / [vllm-bench](https://github.com/vllm-project/vllm-bench) | 对 OpenAI Chat 接口测试输入/输出长度、请求速率、最大并发、TTFT/TPOT/ITL/端到端延迟；保存逐次结果，做并发扫描及多轮结果比较。 | 更适合作为服务端压测方法参考；不要默认某个后端专有的控制参数也被百炼支持。 |
| [GenAI-Perf](https://docs.nvidia.com/deeplearning/triton-inference-server/archives/triton-inference-server-2520/user-guide/docs/perf_analyzer/genai-perf/README.html) | 区分每请求延迟、首 token、token 间隔、整体 output token/s 与 req/s，并导出 CSV/JSON。 | 安装与运行链路相对重；本项目先沿用其指标定义，不引入整套工具。 |
| [LLMPerf](https://github.com/ray-project/llmperf) | 面向 LLM API 的并发请求、逐请求指标和汇总结果。 | 其示例用统一的 Llama tokenizer 估计 token；若两端使用不同 tokenizer，不能把该估计当成各自真实 token 数。 |

## 统一请求负载

1. **接口形式**：两端都通过 OpenAI 兼容的 `chat/completions` 请求；压测客户端、请求体和计时代码相同。先测 `stream=true`，另以非流式请求检查总耗时。若本地服务不是此接口，需要适配层，不把适配层开销藏起来。
2. **固定用例**：把 prompts、messages、目标长度档和随机种子保存为版本化文件。正式无缓存测试使用不同前缀，避免重复文本意外命中缓存；缓存性能另设重复前缀场景。
3. **长度档**：建议先用短、中、长三档目标输入/输出量，例如约 `128/128`、`1024/256`、`4096/512` token。`max_tokens` 只是上限；最终按两端的**实际输入和输出长度分布**复核是否可比，不把不同长度的响应直接混算。
4. **生成参数**：尽量统一模型版本、量化方式、temperature、top_p、输出上限、stop 和上下文模板，并完整记录不支持的参数。若模型不同，性能结论必须同时注明模型差异。

## 负载档位与执行顺序

先用少量请求验证接口、流式事件、实际输出长度和预计用量；这一步不形成性能结论。当前先固定**并发 4**，以每轮 100 条短输入请求检查客户端实际分布；正式稳定性结论仍需至少三次独立运行，并按两端限流、token 用量确定样本数。只有需要寻找饱和点时才扩展并发档，再单独增加固定请求到达率测试；**固定并发**和**固定到达率**的结果分别展示。GuideLLM 也把这些作为不同负载模式，并支持 warmup/cooldown。[方法说明](https://github.com/vllm-project/guidellm#benchmark-controls)

两端尽量从**同一台客户端、同一网络位置**发起测试；远程 API 的广域网与本地接口的网络耗时都计入客户端观测值。不要把本地服务端内部计时与远程 API 的端到端计时放在同一列。记录测试时间、客户端位置、API 地域、本地硬件、版本、速率限制、重试策略和连接复用设置。

## 必报指标

| 指标 | 口径 |
| --- | --- |
| 成功率、错误率 | 所有发出的请求均进入分母；分别统计超时、HTTP 429、HTTP 5xx、断流和空回答。失败请求不混入成功请求的延迟分位数。 |
| E2E 延迟 | 客户端发出请求至收到完整流式结束标志；报 p50、p95，并记录样本量。 |
| 首生成事件与首段可见文本时间 | 客户端分别记录从请求发出至首个非空生成事件、至首个可见 `content` 的时间。若先返回 `reasoning_content`，两者会不同；SSE 事件可能含多个 token，因此只有确认事件对应 token 时才把前者称为严格的 TTFT。GuideLLM 也区分首 token 与首段可见输出。[指标口径](https://github.com/vllm-project/guidellm/blob/main/docs/en/guides/metrics.md) |
| token 间隔 / TPOT | 只在流式结果可可靠计数时计算；一次 SSE 事件不一定等于一个 token，不能直接把事件间隔当作 token 间隔。 |
| 吞吐 | `成功请求数 / 测量窗口秒数`，单位 req/s；`成功请求的实际输出 token 总数 / 测量窗口秒数`，单位 token/s。与“每请求平均 token/s”分开报告。 |
| 输出长度 | 报输入/输出 token 的实际分布；若两端 tokenizer 或 reasoning token 统计不同，分别列服务器 `usage` 与统一口径计算的**可见文本**长度，不把两种 token 计数混为一个速度。 |
| 缓存 | 无缓存与重复前缀分开运行；有 `cached_tokens` 时报告后续请求的缓存 token 比例。服务端未提供可比计数时只报告延迟变化，不推断精确命中率。 |

GuideLLM 的指标文档也指出，少量请求下 p95/p99 的估计很不稳定，因此正式报告必须同时写样本量和多轮结果。[统计说明](https://github.com/vllm-project/guidellm/blob/main/docs/en/guides/metrics.md)

## 输出与比较

- 每条请求保存：场景、端点标签、时间戳、并发档、请求是否成功、HTTP 状态、输入/输出长度、E2E、首生成事件时间、首段可见文本时间、SSE 事件时间和服务端 usage。密钥和完整鉴权头不保存。
- 每个场景分别汇总 p50/p95、req/s、token/s、错误率及样本量；PDF 先给 **API 与本地接口并排表**，再给各场景曲线与逐次数据文件路径。
- 只有同场景、同计时口径、相近实际输出长度的两组结果才给“快多少倍”的结论；任何限流、重试、缓存或模型差异都在结果旁标注。

## 当前实现与正式方案的差距

旧的七项自写评测和性能基线已经移除。新入口使用固定负载规格、同一个流式客户端、预热、并发档和逐请求时间戳；小规模 smoke 仍只用于兼容性检查。当前尚未接入本地模型接口，也未生成双端并排 PDF。正式比较前需获取本地接口、按两端实际输入/输出长度核对负载，并按 API 限流和 token 用量确定足够的采集样本数。LLMPerf 上游的统一 tokenizer 估计值不作为本项目的真实 token 统计；本项目仅报告服务端 usage，并单独记录可见正文长度。
