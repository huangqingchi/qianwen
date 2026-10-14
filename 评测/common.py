"""七项评测共用的请求层：组装 HTTP 请求、读取响应、记录请求摘要。

各 test.py 负责出题和判对错；这里不决定模型能力分数，也不自动重试。
"""

from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def post_chat(base_url: str, api_key: str, payload: dict, timeout: int) -> dict:
    # 所有测试都调用同一个 /chat/completions 接口；模型和消息在 payload 中。
    # 密钥只放进请求头，不写入结果文件。
    request = Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout) as response:
            if payload.get("stream"):
                # 流式响应按 SSE 的 data: 行读取；收到 [DONE] 才算完整结束。
                chunks = []
                first_token_ms = first_visible_ms = usage = None
                events = 0
                done = False
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        done = True
                        break
                    try:
                        event = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    events += 1
                    if event.get("usage"):
                        usage = event["usage"]
                    for choice in event.get("choices") or []:
                        delta = choice.get("delta") or {}
                        content = delta.get("content") or ""
                        # “首令牌”可能是推理内容；“首段可见文本”只看普通正文。
                        if (delta.get("reasoning_content") or content) and first_token_ms is None:
                            first_token_ms = round((time.perf_counter() - start) * 1000, 2)
                        if content:
                            if first_visible_ms is None:
                                first_visible_ms = round((time.perf_counter() - start) * 1000, 2)
                            chunks.append(content)
                return {
                    "status": response.status,
                    "latency_ms": round((time.perf_counter() - start) * 1000, 2),
                    "first_token_ms": first_token_ms,
                    "first_visible_ms": first_visible_ms,
                    "content": "".join(chunks), "usage": usage, "events": events,
                    "done": done, "content_type": response.headers.get("Content-Type", ""),
                }
            # 非流式响应一次性读取 JSON，再抽取首个候选回答和用量。
            data = json.load(response)
            choices = data.get("choices") or []
            message = (choices[0].get("message") or {}) if choices else {}
            return {
                "status": response.status,
                "latency_ms": round((time.perf_counter() - start) * 1000, 2),
                "content": message.get("content") or "", "usage": data.get("usage"),
                "id_present": bool(data.get("id")), "object": data.get("object"),
                "model": data.get("model"), "role": message.get("role"),
                "finish_reason": choices[0].get("finish_reason") if choices else None,
                "content_type": response.headers.get("Content-Type", ""),
            }
    except HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {"message": raw[:500]}
        if not isinstance(body, dict):
            body = {"message": raw[:500]}
        nested = body.get("error") if isinstance(body.get("error"), dict) else {}
        return {
            "status": error.code,
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            "error_code": str(body.get("code") or nested.get("code") or "").replace(api_key, "[KEY]"),
            "error_message": str(body.get("message") or nested.get("message") or "")[:500].replace(api_key, "[KEY]"),
        }
    except (URLError, TimeoutError, OSError) as error:
        return {
            "status": None,
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            "error_code": type(error).__name__,
            "error_message": str(error)[:500].replace(api_key, "[KEY]"),
        }


def call(ctx: dict, messages: list[dict], **extra: object) -> dict:
    # 普通测试统一从这里发请求，并把状态、耗时和用量记入 ctx["calls"]。
    payload = {"model": ctx["model"], "messages": messages, **extra}
    result = post_chat(ctx["base_url"], ctx["api_key"], payload, ctx["timeout"])
    track(ctx, result, bool(extra.get("stream")))
    return result


def track(ctx: dict, result: dict, stream: bool = False, intentional_error: bool = False) -> None:
    ctx["calls"].append({
        "status": result.get("status"), "latency_ms": result.get("latency_ms"),
        "usage": result.get("usage"), "error_code": result.get("error_code"),
        "stream": stream, "intentional_error": intentional_error,
    })


def check(name: str, passed: bool, **details: object) -> dict:
    return {"name": name, "status": "PASS" if passed else "FAIL", **details}


def filler_words(count: int) -> str:
    terms = ("alpha", "bravo", "cedar", "delta", "ember", "fable", "globe", "harbor")
    return " ".join(terms[i % len(terms)] for i in range(count))
