"""用量统计：分别测普通响应、流式响应，各记 1 个用例。

只检查接口返回的 token 数字是否自洽，不独立计算真实 token 数或费用。
"""

from common import call, check


def run(ctx: dict, profile: dict) -> list[dict]:
    # 两次都是短问题；流式请求显式要求末尾附带 usage，否则可能拿不到用量。
    responses = [
        ("非流式", call(ctx, [{"role": "user", "content": "只回复 OK"}])),
        ("流式", call(ctx, [{"role": "user", "content": "只回复 OK"}],
                      stream=True, stream_options={"include_usage": True})),
    ]
    checks = []
    for name, result in responses:
        # 读取服务端原样返回的输入、输出、合计和缓存 token 数。
        usage = result.get("usage") or {}
        prompt = usage.get("prompt_tokens")
        completion = usage.get("completion_tokens")
        total = usage.get("total_tokens")
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
        # 通过条件：HTTP 200；前三个数是非负整数；合计=输入+输出；
        # 如果提供了缓存数，它也必须是非负整数且不超过输入数。
        valid = (result.get("status") == 200
                 and all(type(x) is int and x >= 0 for x in (prompt, completion, total))
                 and total == prompt + completion
                 and (cached is None or type(cached) is int and 0 <= cached <= prompt))
        checks.append(check(name, valid, status_code=result.get("status"),
                            prompt_tokens=prompt, completion_tokens=completion,
                            total_tokens=total, cached_tokens=cached))
    return checks
