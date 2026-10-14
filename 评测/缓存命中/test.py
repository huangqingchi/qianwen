"""缓存命中：连续发 3 次请求，共用同一段长前缀，短问题各不相同。

只依据服务端上报的 cached_tokens 判定；不拿耗时变化猜测是否命中。
隐式缓存具有不确定性，未命中只记“待确认”。
"""

from common import call, filler_words


def run(ctx: dict, profile: dict) -> list[dict]:
    # 前缀词数由档位配置决定。使用 system 消息，保证三次请求前缀完全一致。
    prefix = "下面是供阅读的固定资料：" + filler_words(profile["cache_prefix_words"])
    measurements = []
    for suffix in ("第一个问题：请回复一。", "第二个问题：请回复二。", "第三个问题：请回复三。"):
        result = call(ctx, [
            {"role": "system", "content": prefix},
            {"role": "user", "content": suffix},
        ])
        usage = result.get("usage") or {}
        measurements.append({
            "status_code": result.get("status"),
            "prompt_tokens": usage.get("prompt_tokens"),
            "cached_tokens": (usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
            "latency_ms": result.get("latency_ms"),
        })
    # 缓存命中率按 token 计算：后两次 cached_tokens 之和 / 后两次 prompt_tokens 之和。
    # 第一次请求只负责预热，不进分母；如果服务端没返回任一次缓存数，则不报百分比。
    repeated = measurements[1:]
    measurable = all(type(item["prompt_tokens"]) is int and item["prompt_tokens"] > 0
                     and type(item["cached_tokens"]) is int
                     and 0 <= item["cached_tokens"] <= item["prompt_tokens"]
                     for item in repeated)
    cache_token_hit_rate_pct = (round(
        sum(item["cached_tokens"] for item in repeated)
        / sum(item["prompt_tokens"] for item in repeated) * 100, 2
    ) if measurable else None)
    # 有请求失败则本项失败；三次输入都达到 1024 token 才继续判断缓存。
    # 1024 是当前脚本采用的最低检查值，实际是否命中仍由服务端决定。
    if any(item["status_code"] != 200 for item in measurements):
        status = "FAIL"
    elif any(type(item["cached_tokens"]) is int
             and (item["cached_tokens"] < 0 or item["cached_tokens"] > item["prompt_tokens"])
             for item in measurements if type(item["prompt_tokens"]) is int):
        status = "FAIL"
    elif not all(type(item["prompt_tokens"]) is int and item["prompt_tokens"] >= 1024
                 for item in measurements):
        status = "INCONCLUSIVE"
    # 只看后两次；即使第一次因先前运行已被预热，也不把它算作本次重复命中。
    elif any(type(item["cached_tokens"]) is int and item["cached_tokens"] > 0
             for item in measurements[1:]):
        status = "PASS"
    else:
        status = "INCONCLUSIVE"
    return [{"name": "重复前缀缓存", "status": status, "measurements": measurements,
             "cache_token_hit_rate_pct": cache_token_hit_rate_pct,
             "note": "缓存命中率=后两次请求的 cached_tokens 总数/输入 token 总数；首次请求不计入。"
                     "隐式缓存不保证命中，只有服务端报告 cached_tokens > 0 才算通过。"}]
