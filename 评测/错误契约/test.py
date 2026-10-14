"""错误契约：故意发 3 种无效请求，检查错误响应是否可识别。

只核对 HTTP 状态码落在允许集合内，且返回非空错误代码；
不校验错误文案全文，也不覆盖所有异常输入。
"""

from common import check, post_chat, track


def run(ctx: dict, profile: dict) -> list[dict]:
    # 每行依次是：用例名、使用的密钥、模型名、消息体、允许的 HTTP 状态码。
    # 无效密钥用固定假值，避免把真实密钥写进报告。
    cases = [
        ("错误模型名", ctx["api_key"], "not-a-real-model-271828",
         [{"role": "user", "content": "test"}], {400, 404}),
        ("无效 API Key", "invalid-key-for-endpoint-evaluation", ctx["model"],
         [{"role": "user", "content": "test"}], {401, 403}),
        ("非法消息格式", ctx["api_key"], ctx["model"],
         "this-is-not-an-array", {400, 422}),
    ]
    checks = []
    for name, key, model, messages, expected_statuses in cases:
        # 这里直接调用 post_chat()，因为正常封装 call() 不方便替换密钥或消息格式。
        result = post_chat(ctx["base_url"], key,
                           {"model": model, "messages": messages}, ctx["timeout"])
        track(ctx, result, intentional_error=True)
        # 三项各算一个用例；出现网络故障或缺少错误代码都判为失败。
        checks.append(check(name, result.get("status") in expected_statuses
                            and bool(result.get("error_code")),
                            status_code=result.get("status"), error_code=result.get("error_code"),
                            error_message=result.get("error_message")))
    return checks
