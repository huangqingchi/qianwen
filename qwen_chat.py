"""从命令行调用阿里云百炼模型。"""

import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "glm-5.3"


def ask_model(api_key: str, base_url: str, model: str, messages: list[dict]) -> str | None:
    body = json.dumps(
        {"model": model, "messages": messages},
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        f"{base_url}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=60) as response:
            result = json.load(response)
    except HTTPError as error:
        try:
            details = json.load(error)
        except (UnicodeDecodeError, json.JSONDecodeError):
            details = {}
        if not isinstance(details, dict):
            details = {}
        nested_error = details.get("error")
        if not isinstance(nested_error, dict):
            nested_error = {}
        code = str(details.get("code") or nested_error.get("code") or "")
        message = str(details.get("message") or nested_error.get("message") or "")
        message = message.replace(api_key, "[API Key 已隐藏]")
        print(f"调用失败：HTTP {error.code} {code}: {message}".strip(), file=sys.stderr)
        if code == "Model.AccessDenied":
            print(
                "请在百炼控制台检查此 Key 所属业务空间是否已授权调用所选模型。",
                file=sys.stderr,
            )
        return None
    except URLError as error:
        print(f"连接失败：{error.reason}", file=sys.stderr)
        return None

    return result["choices"][0]["message"]["content"]


def main() -> int:
    parser = argparse.ArgumentParser(description="向阿里云百炼模型发送消息")
    parser.add_argument("message", nargs="*", help="单次发送的问题；不填则进入持续对话")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"模型名称，默认 {DEFAULT_MODEL}")
    args = parser.parse_args()

    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        parser.error("请先设置 DASHSCOPE_API_KEY 环境变量")
    base_url = os.environ.get("DASHSCOPE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")

    if args.message:
        reply = ask_model(
            api_key, base_url, args.model,
            [{"role": "user", "content": " ".join(args.message)}],
        )
        if reply is None:
            return 1
        print(reply)
        return 0

    print(f"已进入持续对话（{args.model}）。输入 /clear 清空上下文，输入 /exit 退出。")
    messages: list[dict] = []
    try:
        while True:
            message = input("你：").strip()
            if message.lower() in {"/exit", "exit", "退出"}:
                break
            if message.lower() in {"/clear", "clear", "清空"}:
                messages.clear()
                print("上下文已清空。")
                continue
            if not message:
                continue

            pending = [*messages, {"role": "user", "content": message}]
            reply = ask_model(api_key, base_url, args.model, pending)
            if reply is None:
                continue
            print(f"助手：{reply}")
            messages = [*pending, {"role": "assistant", "content": reply}]
    except (KeyboardInterrupt, EOFError):
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
