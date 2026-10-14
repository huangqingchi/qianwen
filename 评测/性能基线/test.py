"""性能基线：测少量串行、并发、流式请求的响应时间。

只输出成功率、P50/P95、首令牌时间等实测值；没有验收阈值时不打性能分。
快速档样本量很小，不能据此推断生产环境的稳定延迟。
"""

import statistics
from concurrent.futures import ThreadPoolExecutor

from common import call


def percentile(values: list[float], fraction: float) -> float | None:
    # 排序后做线性插值；只统计成功且有正文的普通请求。
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    return round(ordered[low] + (ordered[high] - ordered[low]) * (index - low), 2)


def run(ctx: dict, profile: dict) -> list[dict]:
    prompt = "请用约80个汉字说明为什么单次模型回复不能代表整体准确率。"
    # 串行请求一个完成后才发下一个；次数由档位配置决定。
    serial = [call(ctx, [{"role": "user", "content": f"{prompt} 编号{i}"}])
              for i in range(profile["performance_serial_requests"])]

    def parallel_one(index: int) -> dict:
        return call(ctx, [{"role": "user", "content": f"{prompt} 并发编号{index}"}])

    # 并发请求同时发出，worker 数也是档位配置；不计算整批总吞吐。
    with ThreadPoolExecutor(max_workers=profile["performance_workers"]) as pool:
        parallel = list(pool.map(parallel_one, range(profile["performance_parallel_requests"])))
    results = serial + parallel
    good = [item for item in results if item.get("status") == 200 and item.get("content")]
    latencies = [item["latency_ms"] for item in good]
    # “输出令牌/秒”用服务端 completion_tokens 除以端到端时长，
    # 某些推理模型的 completion_tokens 包含推理令牌，所以它不是可见文字生成速度。
    rates = []
    for item in good:
        tokens = (item.get("usage") or {}).get("completion_tokens")
        if type(tokens) is int and item["latency_ms"] > 0:
            rates.append(tokens / (item["latency_ms"] / 1000))
    # 另发一条流式请求，记录首令牌和首段可见文字出现的时间。
    stream = call(ctx, [{"role": "user", "content": "用一句话介绍桂花。"}],
                  stream=True, stream_options={"include_usage": True})
    # 任何请求失败都标“失败”；全部成功则只标“已测量”，仍不换算等级。
    if stream.get("status") != 200 or not stream.get("done"):
        status = "FAIL"
    elif len(good) != len(results):
        status = "FAIL"
    else:
        status = "MEASURED"
    return [{
        "name": "串行、并发、流式时延", "status": status,
        "requested": len(results), "successful": len(good),
        "success_rate": round(len(good) / len(results), 4),
        "latency_p50_ms": percentile(latencies, 0.5),
        "latency_p95_ms": percentile(latencies, 0.95),
        "output_tokens_per_sec_mean": round(statistics.mean(rates), 2) if rates else None,
        "streaming_first_token_ms": stream.get("first_token_ms"),
        "streaming_first_visible_ms": stream.get("first_visible_ms"),
        "note": "未提供性能等级阈值，只有实测值；小样本 P95 仅供观察。",
    }]
