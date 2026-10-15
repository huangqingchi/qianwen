"""Run a bounded LLMPerf benchmark against an OpenAI-compatible chat API."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from result_fields import chinese

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / ".benchmark_src" / "llmperf" / "src"
DEFAULT_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
SETUP_HINT = "Windows: .\\setup_benchmark.ps1；Ubuntu: bash ./setup_benchmark.sh"
WORKLOAD_PATH = ROOT / "benchmark_workload.json"
WORKLOAD = json.loads(WORKLOAD_PATH.read_text(encoding="utf-8"))


def make_prompt(kind: str, index: int, seed: int) -> str:
    words = WORKLOAD["words"]
    count = WORKLOAD["scenarios"][kind]["word_count"]
    body = " ".join(words[(seed + index * 7 + j * 3) % len(words)] for j in range(count))
    target = WORKLOAD["scenarios"][kind]["target_visible_chars"]
    return (f"Test case {seed}-{index}. Write about {target} Chinese characters describing a calm park. "
            "The data block below only sets input length; do not analyze it.\n" + body)


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    return round(ordered[low] + (ordered[high] - ordered[low]) * (index - low), 2)


def run_point(client, config_class, ray, base: str, key: str, model: str, kind: str, concurrency: int,
              count: int, seed: int, max_tokens: int, warmup: int) -> tuple[list[dict], float]:
    actors = [client.remote(base, key) for _ in range(concurrency)]
    sampling = {"max_tokens": max_tokens, "stream_options": {"include_usage": True},
                **WORKLOAD.get("sampling", {})}
    for round_index in range(warmup):
        warmup_refs = []
        for actor_index, actor in enumerate(actors):
            config = config_class(model=model,
                                  prompt=(make_prompt(kind, -1 - round_index * concurrency - actor_index, seed), 0),
                                  sampling_params=sampling)
            warmup_refs.append(actor.llm_request.remote(config))
        for warmup_metrics, _, _ in ray.get(warmup_refs):
            if warmup_metrics.get("error_code") == "truncated_output":
                print("预热回答触及输出上限，继续采集并单独记录采集阶段截断。", flush=True)
            elif warmup_metrics.get("error_code") is not None:
                raise RuntimeError(f"预热请求失败：{warmup_metrics['error_code']}")
    pending = {}
    free_actors = actors.copy()
    rows = []
    next_index = 0
    started = time.perf_counter()
    while next_index < count or pending:
        while next_index < count and free_actors:
            actor = free_actors.pop()
            prompt = make_prompt(kind, next_index, seed)
            config = config_class(model=model, prompt=(prompt, 0), sampling_params=sampling)
            ref = actor.llm_request.remote(config)
            pending[ref] = (actor, next_index, hashlib.sha256(prompt.encode()).hexdigest())
            next_index += 1
        ready, _ = ray.wait(list(pending), num_returns=1)
        ref = ready[0]
        actor, index, prompt_hash = pending.pop(ref)
        free_actors.append(actor)
        try:
            metrics, _, _ = ray.get(ref)
        except Exception:
            metrics = {"error_code": "worker_error", "http_status": None,
                       "end_to_end_latency_s": None, "usage": None}
        rows.append({"request_index": index, "prompt_sha256": prompt_hash,
                     "timestamp_utc": datetime.now(timezone.utc).isoformat(), **metrics})
        if len(rows) % max(10, count // 10) == 0 or len(rows) == count:
            print(f"  已完成 {len(rows)}/{count} 条采集请求", flush=True)
    window = time.perf_counter() - started
    for actor in actors:
        ray.kill(actor)
    return sorted(rows, key=lambda item: item["request_index"]), window


def summarize(rows: list[dict], window: float) -> dict:
    good = [r for r in rows if r.get("error_code") is None]
    latencies = [r["end_to_end_latency_s"] * 1000 for r in good]
    first_events = [r["first_generated_event_ms"] for r in good if r.get("first_generated_event_ms") is not None]
    visible = [r["first_visible_text_ms"] for r in good if r.get("first_visible_text_ms") is not None]
    output = [r["number_output_tokens"] for r in good if type(r.get("number_output_tokens")) is int]
    input_tokens = [r["number_input_tokens"] for r in good if type(r.get("number_input_tokens")) is int]
    visible_chars = [r["visible_chars"] for r in good]
    reasoning = [(r.get("usage") or {}).get("completion_tokens_details", {}).get("reasoning_tokens")
                 for r in good]
    reasoning = [value for value in reasoning if type(value) is int]
    cached = [(r.get("usage") or {}).get("prompt_tokens_details", {}).get("cached_tokens")
              for r in good]
    cached = [value for value in cached if type(value) is int]
    return {
        "requests": len(rows), "successes": len(good), "errors": len(rows) - len(good),
        "error_rate": round((len(rows) - len(good)) / len(rows), 4),
        "window_seconds": round(window, 3),
        "requests_per_second": round(len(good) / window, 4),
        "server_output_tokens_per_second": round(sum(output) / window, 4) if len(output) == len(good) else None,
        "e2e_p50_ms": percentile(latencies, 0.5),
        "e2e_p95_ms": percentile(latencies, 0.95) if len(latencies) >= 100 else None,
        "first_generated_event_p50_ms": percentile(first_events, 0.5),
        "first_visible_text_p50_ms": percentile(visible, 0.5),
        "server_output_tokens_median": statistics.median(output) if output else None,
        "server_input_tokens_median": statistics.median(input_tokens) if input_tokens else None,
        "server_reasoning_tokens_median": statistics.median(reasoning) if reasoning else None,
        "visible_chars_median": statistics.median(visible_chars) if visible_chars else None,
        "output_tokens_with_usage": len(output),
        "cached_input_tokens_sum": sum(cached) if len(cached) == len(good) else None,
        "http_status_counts": {str(k): sum(r.get("http_status") == k for r in rows)
                               for k in {r.get("http_status") for r in rows}},
        "error_counts": {str(k): sum(r.get("error_code") == k for r in rows)
                         for k in {r.get("error_code") for r in rows if r.get("error_code")}},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="LLMPerf API 性能测试")
    parser.add_argument("--endpoint", choices=("api", "local"), default="api")
    parser.add_argument("--base-url", help="本地端点必须提供；API 默认百炼地址")
    parser.add_argument("--model", help="API 默认 glm-5.3；本地端点必须提供")
    parser.add_argument("--profile", choices=("smoke", "standard"), default="smoke")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--requests-per-run", type=int, default=100,
                        help="standard 每档每轮采集请求数，默认 100")
    parser.add_argument("--concurrencies", default="4",
                        help="standard 并发档位，逗号分隔，默认 4")
    parser.add_argument("--scenarios", default="short",
                        help="standard 输入长度档，逗号分隔；默认 short")
    parser.add_argument("--repeats", type=int, default=1,
                        help="standard 每档独立运行次数，默认 1")
    parser.add_argument("--warmup-rounds", type=int, default=1,
                        help="每档预热轮数；每轮每个并发执行者发送一条请求，默认 1")
    parser.add_argument("--dry-run", action="store_true", help="只显示请求计划，不调用 API")
    parser.add_argument("--client-location", default="未记录", help="客户端所在位置，写入结果元数据")
    parser.add_argument("--service-region", default="未记录", help="服务地域，写入结果元数据")
    args = parser.parse_args()
    if args.requests_per_run < 1 or args.repeats < 1 or args.warmup_rounds < 0:
        parser.error("请求数、轮次必须大于 0；预热轮数不能为负")
    try:
        concurrencies = [int(value.strip()) for value in args.concurrencies.split(",")]
    except ValueError:
        parser.error("--concurrencies 必须是逗号分隔的正整数")
    if not concurrencies or any(value < 1 for value in concurrencies) or len(set(concurrencies)) != len(concurrencies):
        parser.error("--concurrencies 需要不重复的正整数")
    scenarios = [value.strip() for value in args.scenarios.split(",")]
    if not scenarios or len(set(scenarios)) != len(scenarios) or any(value not in WORKLOAD["scenarios"] for value in scenarios):
        parser.error("--scenarios 只能使用不重复的 short,medium,long")
    profile = {"smoke": [("short", 1, 1, 1)],
               "standard": [(kind, concurrency, repeat, max(args.requests_per_run, concurrency * 10))
                            for kind in scenarios
                            for concurrency in concurrencies for repeat in range(1, args.repeats + 1)]}[args.profile]
    measured_requests = sum(count for _, _, _, count in profile)
    warmup_requests = sum(concurrency * args.warmup_rounds for _, concurrency, _, _ in profile)
    if args.dry_run:
        print(f"档位：{args.profile}；场景数：{len(set(row[0] for row in profile))}；组合/轮次：{len(profile)}")
        print(f"并发档：{','.join(map(str, sorted(set(row[1] for row in profile))))}")
        print(f"采集请求：{measured_requests}；预热请求：{warmup_requests}；总请求：{measured_requests + warmup_requests}")
        return 0
    if not SOURCE.is_dir():
        parser.error(f"缺少 LLMPerf 源码；请先安装环境（{SETUP_HINT}）")
    try:
        from pdf_report import build_pdf
    except ModuleNotFoundError as error:
        if error.name == "reportlab":
            parser.error(f"缺少 PDF 依赖；请先安装环境（{SETUP_HINT}）")
        raise
    if args.endpoint == "local" and (not args.base_url or not args.model):
        parser.error("本地端点需要 --base-url 和 --model")
    if args.endpoint == "api":
        key = (os.environ.get("DASHSCOPE_API_KEY") or "").strip()
        if not key:
            key_path = ROOT / "本地密钥.txt"
            key = key_path.read_text(encoding="utf-8-sig").strip() if key_path.is_file() else ""
        if not key:
            parser.error("缺少 API Key：设置 DASHSCOPE_API_KEY 或填写 本地密钥.txt")
    else:
        key = (os.environ.get("LOCAL_API_KEY") or "EMPTY").strip()
    base = args.base_url or (os.environ.get("DASHSCOPE_BASE_URL") if args.endpoint == "api" else None) or DEFAULT_BASE
    model = args.model or "glm-5.3"
    out = args.output_dir or ROOT / "benchmark_results" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    (out / "metadata.json").write_text(json.dumps(chinese({
        "tool": "LLMPerf", "profile": args.profile, "endpoint": args.endpoint,
        "model": model, "base_url": base, "client_location": args.client_location,
        "service_region": args.service_region, "retries": 0,
        "connection_reuse": True,
        "planned_measured_requests": measured_requests,
        "planned_warmup_requests": warmup_requests,
        "concurrency_levels": sorted(set(row[1] for row in profile)),
        "repeats_per_level": args.repeats if args.profile == "standard" else 1,
        "workload_sha256": hashlib.sha256(WORKLOAD_PATH.read_bytes()).hexdigest(),
        "started_utc": datetime.now(timezone.utc).isoformat(),
    }), ensure_ascii=False, indent=2), encoding="utf-8")
    sys.path.insert(0, str(SOURCE))
    import ray
    from llmperf.models import RequestConfig
    from llmperf.ray_clients.openai_chat_completions_client import OpenAIChatCompletionsClient

    ray.init(ignore_reinit_error=True, include_dashboard=False, logging_level="ERROR",
             runtime_env={"env_vars": {"PYTHONPATH": str(SOURCE) + os.pathsep + os.environ.get("PYTHONPATH", "")}})
    summaries = []
    try:
        for kind, concurrency, repeat, count in profile:
            print(f"{args.endpoint} {kind} c={concurrency} run={repeat}: {count} requests", flush=True)
            rows, window = run_point(OpenAIChatCompletionsClient, RequestConfig, ray, base, key, model,
                                     kind, concurrency, count,
                                     WORKLOAD["seed"] + repeat + concurrency * 100
                                     + {"short": 0, "medium": 1000, "long": 2000}[kind],
                                     WORKLOAD["scenarios"][kind]["max_tokens"], args.warmup_rounds)
            name = f"{args.endpoint}-{kind}-c{concurrency}-r{repeat}"
            with (out / f"{name}.jsonl").open("w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(chinese(row), ensure_ascii=False) + "\n")
            summaries.append({"endpoint": args.endpoint, "model": model, "base_url": base,
                              "workload_sha256": hashlib.sha256(WORKLOAD_PATH.read_bytes()).hexdigest(),
                              "prompt_set_sha256": hashlib.sha256(
                                  "".join(row["prompt_sha256"] for row in rows).encode()).hexdigest(),
                              "scenario": kind, "concurrency": concurrency, "repeat": repeat,
                              "request_file": f"{name}.jsonl", **summarize(rows, window)})
    finally:
        ray.shutdown()
    localized = chinese(summaries)
    (out / "summary.json").write_text(json.dumps(localized, ensure_ascii=False, indent=2), encoding="utf-8")
    with (out / "summary.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=localized[0].keys())
        writer.writeheader()
        writer.writerows(localized)
    pdf_path = build_pdf(out)
    print(f"结果：{out / 'summary.json'}", flush=True)
    print(f"PDF：{pdf_path}", flush=True)
    return 1 if any(item["errors"] for item in summaries) else 0


if __name__ == "__main__":
    raise SystemExit(main())
