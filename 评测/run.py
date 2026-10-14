"""运行全部或单项评测，并为每项生成独立结果。"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
QWEN_DIR = ROOT.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(QWEN_DIR))
ITEMS = ("接口契约", "错误契约", "用量统计", "长上下文", "缓存命中", "固定题集精度", "性能基线")
PROFILE_NAMES = {"smoke": "快速", "standard": "标准", "extended": "扩展"}
STATUS_NAMES = {"PASS": "通过", "FAIL": "失败", "ERROR": "执行出错",
                "INCONCLUSIVE": "待确认", "MEASURED": "已测量"}
FIELD_NAMES = {
    "name": "用例名称", "status": "结果", "status_code": "HTTP状态码",
    "object": "对象类型", "role": "消息角色", "answer": "模型回答",
    "events": "流式事件数", "done": "正常结束", "error_code": "错误代码",
    "error_message": "错误信息", "error_type": "错误类型",
    "prompt_tokens": "输入令牌数", "completion_tokens": "输出令牌数",
    "total_tokens": "令牌总数", "cached_tokens": "缓存令牌数",
    "latency_ms": "耗时（毫秒）", "expected": "预期结果", "actual": "实际结果",
    "category": "题目类别", "measurements": "请求测量", "note": "说明",
    "requested": "请求数", "successful": "成功数", "success_rate": "成功率",
    "latency_p50_ms": "耗时P50（毫秒）", "latency_p95_ms": "耗时P95（毫秒）",
    "output_tokens_per_sec_mean": "平均输出令牌速度（每秒）",
    "streaming_first_token_ms": "流式首令牌时间（毫秒）",
    "streaming_first_visible_ms": "流式首段可见文本时间（毫秒）",
    "usage": "令牌用量", "stream": "流式请求",
    "intentional_error": "预期错误请求",
    "prompt_tokens_details": "输入令牌详情",
    "completion_tokens_details": "输出令牌详情",
    "reasoning_tokens": "推理令牌数",
}


def chinese_fields(value: object, request: bool = False) -> object:
    """只在写结果时翻译字段；测试内部仍使用接口原始字段。"""
    if isinstance(value, dict):
        translated = {}
        for key, item in value.items():
            label = "HTTP状态码" if request and key == "status" else FIELD_NAMES.get(key, key)
            if key == "status" and not request:
                item = STATUS_NAMES.get(item, item)
            translated[label] = chinese_fields(item)
        return translated
    if isinstance(value, list):
        return [chinese_fields(item) for item in value]
    return value


def readable(value: object) -> str:
    if value is True:
        return "是"
    if value is False:
        return "否"
    if value is None:
        return "未提供"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def score(checks: list[dict], item: str) -> dict:
    # 每项单独算：通过数 / (通过数 + 失败数) × 100；各用例等权。
    # 缓存“待确认”和性能“已测量”不进分母；性能没有阈值，因此始终不打分。
    # 这是脚本内定义的用例通过率，不是照片中的等级标准。
    passed = sum(item["status"] == "PASS" for item in checks)
    failed = sum(item["status"] in {"FAIL", "ERROR"} for item in checks)
    denominator = passed + failed
    return {
        "passed": passed, "failed": failed,
        "inconclusive": sum(item["status"] == "INCONCLUSIVE" for item in checks),
        "measured": sum(item["status"] == "MEASURED" for item in checks),
        "score": round(passed / denominator * 100, 2)
        if denominator and item != "性能基线" else None,
    }


def save_item(out_dir: Path, item: str, model: str, base_url: str,
              profile: str, checks: list[dict], calls: list[dict],
              time_utc: str | None = None) -> dict:
    folder = out_dir / item
    folder.mkdir(parents=True, exist_ok=True)
    tally = score(checks, item)
    result = {
        "item": item, "model": model, "base_url": base_url, "profile": profile,
        "time_utc": time_utc or datetime.now(timezone.utc).isoformat(),
        "score": tally, "checks": checks, "calls": calls,
    }
    translated = {
        "项目": item, "模型": model, "接口地址": base_url,
        "测试档位": PROFILE_NAMES.get(profile, profile),
        "测试时间（UTC）": result["time_utc"],
        "计分": {
            "通过数": tally["passed"], "失败数": tally["failed"],
            "待确认数": tally["inconclusive"], "仅测量数": tally["measured"],
            "本地用例分数": tally["score"],
        },
        "用例结果": [chinese_fields(entry) for entry in checks],
        "请求记录": [chinese_fields(entry, request=True) for entry in calls],
    }
    (folder / "结果.json").write_text(json.dumps(translated, ensure_ascii=False, indent=2), encoding="utf-8")
    score_text = f"{tally['score']:g} 分（满分 100 分）" if tally["score"] is not None else "未评分"
    lines = [f"# {item}", "", f"模型：`{model}`　档位：{PROFILE_NAMES.get(profile, profile)}", "",
             f"**本地用例分数：{score_text}**", "",
             f"通过 {tally['passed']} 项；失败 {tally['failed']} 项；"
             f"待确认 {tally['inconclusive']} 项；仅测量 {tally['measured']} 项。", "",
             "分数只按本项有明确对错的用例计算；待确认和仅测量不计入分母。", "",
             "| 用例 | 结果 | 证据 |", "| --- | --- | --- |"]
    for item_result in checks:
        details = chinese_fields({k: v for k, v in item_result.items()
                                  if k not in {"name", "status"}})
        detail_text = "；".join(f"{key}：{readable(value)}" for key, value in details.items())
        detail_text = detail_text.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {item_result['name']} | {STATUS_NAMES.get(item_result['status'], item_result['status'])} | "
                     f"{detail_text} |")
    lines += ["", "具体请求统计见 [结果.json](结果.json)。", ""]
    (folder / "报告.md").write_text("\n".join(lines), encoding="utf-8")
    return result


def write_overview(out_dir: Path, model: str, profile: str, overview: list[dict]) -> None:
    lines = ["# 本次评测总览", "", f"模型：`{model}`　档位：{PROFILE_NAMES.get(profile, profile)}", "",
             "| 项目 | 本地用例分数 | 通过 | 失败 | 待确认 | 仅测量 |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for entry in overview:
        value = f"{entry['score']:g} 分" if entry["score"] is not None else "未评分"
        lines.append(f"| [{entry['item']}]({entry['item']}/报告.md) | {value} | "
                     f"{entry['passed']} | {entry['failed']} | "
                     f"{entry['inconclusive']} | {entry['measured']} |")
    lines += ["", "分数是本地用例通过率，不代表照片里的等级；照片中的阈值尚未录入。", ""]
    (out_dir / "总览.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="按评分项运行百炼模型评测")
    parser.add_argument("--item", choices=ITEMS, help="只测试这一项；不填则依次测试全部")
    parser.add_argument("--profile", choices=("smoke", "standard", "extended"))
    parser.add_argument("--model")
    parser.add_argument("--base-url")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--context-words", type=int, help="额外测试指定填充词长度")
    parser.add_argument("--only-long-context", action="store_true", help="长上下文只测试指定长度")
    parser.add_argument("--output-dir", type=Path, help="本次运行的结果根目录")
    parser.add_argument("--list", action="store_true", help="列出可单独运行的项目")
    args = parser.parse_args()
    if args.list:
        print("\n".join(ITEMS))
        return 0
    if args.timeout < 1:
        parser.error("--timeout 必须是正整数")
    if args.context_words is not None and args.context_words < 10:
        parser.error("--context-words 至少为 10")
    if args.only_long_context and (args.item != "长上下文" or args.context_words is None):
        parser.error("--only-long-context 需要 --item 长上下文 和 --context-words")

    from qwen_chat import DEFAULT_BASE_URL, DEFAULT_MODEL, load_api_key

    config = json.loads((QWEN_DIR / "eval_config.json").read_text(encoding="utf-8"))
    profile_name = args.profile or config["default_profile"]
    profile = config["profiles"][profile_name]
    api_key = load_api_key()
    if not api_key:
        parser.error("请填写项目根目录的 本地密钥.txt，或设置 DASHSCOPE_API_KEY")
    base_url = args.base_url or os.environ.get("DASHSCOPE_BASE_URL") or DEFAULT_BASE_URL
    model = args.model or config.get("model") or DEFAULT_MODEL
    # 默认结果写在项目内部；相对的 --output-dir 也以项目根目录为基准。
    # Path 会按当前系统处理 Windows/Ubuntu 的分隔符和绝对路径。
    out_dir = args.output_dir or ROOT / "结果" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    if not out_dir.is_absolute():
        out_dir = QWEN_DIR / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    # 指定 --item 只跑一项；不指定才按顺序运行七项。
    selected = [args.item] if args.item else list(ITEMS)
    overview = []
    for index, item in enumerate(selected, 1):
        print(f"[{index}/{len(selected)}] {item}", flush=True)
        # 每项重新建请求记录，确保报告和分数互相独立。
        ctx = {"api_key": api_key, "base_url": base_url, "model": model,
               "timeout": args.timeout, "calls": [],
               "context_words": args.context_words, "only_long_context": args.only_long_context}
        try:
            checks = importlib.import_module(f"{item}.test").run(ctx, profile)
        except Exception as error:
            checks = [{"name": "测试执行", "status": "ERROR",
                       "error_type": type(error).__name__,
                       "error_message": str(error).replace(api_key, "[KEY]")[:500]}]
        result = save_item(out_dir, item, model, base_url, profile_name, checks, ctx["calls"])
        overview.append({"item": item, **result["score"]})
        value = (f"{result['score']['score']:g} 分" if result["score"]["score"] is not None
                 else "未评分")
        print(f"  分数：{value}；报告：{out_dir / item / '报告.md'}", flush=True)

    write_overview(out_dir, model, profile_name, overview)
    print(f"总览：{out_dir / '总览.md'}", flush=True)
    return 1 if any(item["failed"] for item in overview) else 0


if __name__ == "__main__":
    raise SystemExit(main())
