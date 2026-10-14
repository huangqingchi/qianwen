"""长上下文：对配置中的每个长度各发 1 次请求。

在重复填充词的约 10%、50%、90% 处放入标记，要求模型按顺序找回。
这只是合成长文本的定点检索，不是复杂长文理解或最大窗口认证。
"""

import re

from common import call, check, filler_words


def run(ctx: dict, profile: dict) -> list[dict]:
    # smoke/standard/extended 的长度来自项目根目录的 eval_config.json。
    # --only-long-context 会只测命令行指定的长度，避免重复发送长请求。
    counts = list(profile["long_context_words"])
    if ctx.get("context_words") is not None:
        counts = [ctx["context_words"]] if ctx.get("only_long_context") else counts + [ctx["context_words"]]
    checks = []
    for count in counts:
        # 使用重复的英文词填充；count 是“词数”，不是模型的 token 数。
        words = filler_words(count).split(" ")
        markers = ("MARKER-A7K2", "MARKER-B4Q9", "MARKER-C8M3")
        for position, marker in zip((0.1, 0.5, 0.9), markers):
            words[int(count * position)] = marker
        prompt = (" ".join(words) + "\n请按出现顺序列出上文三个以 MARKER- 开头的代号，"
                  "只输出代号并用空格分隔。")
        result = call(ctx, [{"role": "user", "content": prompt}])
        # 只从最终回答提取 MARKER-... 并比较顺序；真实输入 token 数来自服务端 usage。
        found = re.findall(r"MARKER-[A-Z0-9]+", result.get("content", ""))
        usage = result.get("usage") or {}
        checks.append(check(f"填充词 {count}", result.get("status") == 200
                            and found == list(markers),
                            status_code=result.get("status"),
                            prompt_tokens=usage.get("prompt_tokens"),
                            expected=list(markers), actual=found,
                            latency_ms=result.get("latency_ms"),
                            error_code=result.get("error_code")))
    return checks
