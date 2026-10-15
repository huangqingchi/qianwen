"""Chinese field names for saved benchmark results."""

FIELDS = {
    "request_index": "请求序号",
    "prompt_sha256": "提示词SHA256",
    "timestamp_utc": "完成时间UTC",
    "error_code": "错误代码",
    "error_msg": "错误信息",
    "ttft_s": "首生成事件耗时秒",
    "end_to_end_latency_s": "端到端耗时秒",
    "inter_token_latency_s": "token间隔秒",
    "number_input_tokens": "输入token数",
    "number_output_tokens": "输出token数",
    "number_total_tokens": "总token数",
    "request_output_throughput_token_per_s": "单请求输出token每秒",
    "http_status": "HTTP状态码",
    "done": "收到流结束标志",
    "finish_reason": "结束原因",
    "first_generated_event_ms": "首生成事件耗时毫秒",
    "first_visible_text_ms": "首段可见文本耗时毫秒",
    "generated_event_ms": "生成事件时间毫秒",
    "visible_chars": "可见文本字符数",
    "usage": "服务端用量",
    "requested_input_tokens_estimate": "请求输入token估算数",
    "prompt_tokens": "输入token数",
    "completion_tokens": "输出token数",
    "total_tokens": "总token数",
    "prompt_tokens_details": "输入token详情",
    "completion_tokens_details": "输出token详情",
    "reasoning_tokens": "推理token数",
    "cached_tokens": "缓存token数",
    "tool": "测试工具",
    "profile": "测试档位",
    "endpoint": "端点标签",
    "model": "模型",
    "base_url": "接口地址",
    "client_location": "客户端位置",
    "service_region": "服务地域",
    "retries": "重试次数",
    "connection_reuse": "连接复用",
    "planned_measured_requests": "计划采集请求数",
    "planned_warmup_requests": "计划预热请求数",
    "concurrency_levels": "并发档位",
    "repeats_per_level": "每档运行轮次",
    "workload_sha256": "负载文件SHA256",
    "started_utc": "开始时间UTC",
    "prompt_set_sha256": "提示词集合SHA256",
    "scenario": "场景",
    "concurrency": "并发数",
    "repeat": "轮次",
    "request_file": "逐请求文件",
    "requests": "请求数",
    "successes": "成功数",
    "errors": "失败数",
    "error_rate": "错误率",
    "window_seconds": "测量窗口秒",
    "requests_per_second": "成功请求每秒",
    "server_output_tokens_per_second": "服务端输出token每秒",
    "e2e_p50_ms": "端到端P50毫秒",
    "e2e_p95_ms": "端到端P95毫秒",
    "first_generated_event_p50_ms": "首生成事件P50毫秒",
    "first_visible_text_p50_ms": "首段可见文本P50毫秒",
    "server_output_tokens_median": "服务端输出token中位数",
    "server_input_tokens_median": "服务端输入token中位数",
    "server_reasoning_tokens_median": "服务端推理token中位数",
    "visible_chars_median": "可见文本字符中位数",
    "output_tokens_with_usage": "提供输出用量的请求数",
    "cached_input_tokens_sum": "缓存输入token合计",
    "http_status_counts": "HTTP状态分布",
    "error_counts": "错误类别分布",
}

SUMMARY_FIELDS = {
    key: FIELDS[key] for key in (
        "endpoint", "model", "base_url", "workload_sha256", "prompt_set_sha256",
        "scenario", "concurrency", "repeat", "request_file", "requests", "successes",
        "errors", "error_rate", "window_seconds", "requests_per_second",
        "server_output_tokens_per_second", "e2e_p50_ms", "e2e_p95_ms",
        "first_generated_event_p50_ms", "first_visible_text_p50_ms",
        "server_output_tokens_median", "server_input_tokens_median",
        "server_reasoning_tokens_median", "visible_chars_median",
        "output_tokens_with_usage", "cached_input_tokens_sum", "http_status_counts",
        "error_counts",
    )
}
ENGLISH_SUMMARY_FIELDS = {value: key for key, value in SUMMARY_FIELDS.items()}

ERROR_NAMES = {
    "truncated_output": "输出截断", "incomplete_stream": "流未完整结束",
    "empty_answer": "空回答", "unexpected_finish_reason": "异常结束原因",
    "invalid_stream": "流格式错误", "timeout": "超时",
    "connection_error": "连接错误", "worker_error": "执行进程错误",
}
ENGLISH_ERROR_NAMES = {value: key for key, value in ERROR_NAMES.items()}


def chinese(value, parent=None):
    if isinstance(value, list):
        return [chinese(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, item in value.items():
        if parent == "http_status_counts":
            label = f"HTTP {key}" if key != "None" else "无HTTP状态码"
        elif parent == "error_counts":
            label = ERROR_NAMES.get(key, key)
        else:
            label = FIELDS.get(key, key)
        result[label] = chinese(item, key)
    return result


def english_summary(row: dict) -> dict:
    """Accept either old English summaries or new Chinese summaries."""
    result = {ENGLISH_SUMMARY_FIELDS.get(key, key): value for key, value in row.items()}
    if "http_status_counts" in result:
        result["http_status_counts"] = {
            (key[5:] if key.startswith("HTTP ") else "None" if key == "无HTTP状态码" else key): value
            for key, value in result["http_status_counts"].items()
        }
    if "error_counts" in result:
        result["error_counts"] = {
            ENGLISH_ERROR_NAMES.get(key, key): value
            for key, value in result["error_counts"].items()
        }
    return result
