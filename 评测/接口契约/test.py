"""接口契约：发 3 次请求，每次对应 1 个通过/失败用例。

这里只检查接口能否按约定返回，不能据此判断回答质量。
"""

from common import call, check


def run(ctx: dict, profile: dict) -> list[dict]:
    # 第 1 次：普通请求。要求 HTTP 200、标准对象类型、assistant 消息、非空回答等。
    # 注意：此处没有检查回答是否严格等于“OK”；它测的是响应结构。
    basic = call(ctx, [{"role": "user", "content": "只回复 OK"}])
    basic_ok = (
        basic.get("status") == 200 and basic.get("id_present")
        and basic.get("object") == "chat.completion"
        and basic.get("role") == "assistant" and bool(basic.get("content"))
        and basic.get("finish_reason") is not None
    )
    checks = [check("非流式返回字段", basic_ok, status_code=basic.get("status"),
                    object=basic.get("object"), role=basic.get("role"))]

    # 第 2 次：一次性提交“用户→助手→用户”三条消息，再看模型能否说出代号。
    # 历史助手消息由脚本直接提供，因此这不是跨请求的长期记忆测试。
    multi = call(ctx, [
        {"role": "user", "content": "请记住代号：VIOLET-27。"},
        {"role": "assistant", "content": "我记住了。"},
        {"role": "user", "content": "刚才的代号是什么？只输出代号。"},
    ])
    checks.append(check("多轮消息", multi.get("status") == 200
                        and "VIOLET-27" in multi.get("content", ""),
                        status_code=multi.get("status"), answer=multi.get("content", "")[:100]))

    # 第 3 次：打开流式输出。检查事件、可见文本、结束标志和 SSE 内容类型。
    # 流式协议的拆包和 [DONE] 读取在 common.py 的 post_chat() 中完成。
    stream = call(ctx, [{"role": "user", "content": "用一句话介绍桂花。"}],
                  stream=True, stream_options={"include_usage": True})
    stream_ok = (
        stream.get("status") == 200 and stream.get("done")
        and stream.get("events", 0) > 0 and bool(stream.get("content"))
        and "text/event-stream" in stream.get("content_type", "")
    )
    checks.append(check("流式 SSE", stream_ok, status_code=stream.get("status"),
                        events=stream.get("events"), done=stream.get("done")))
    return checks
