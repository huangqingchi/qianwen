"""Compare two benchmark summaries without sending requests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from result_fields import english_summary


def load(path: Path) -> dict:
    rows = [english_summary(row) for row in json.loads(path.read_text(encoding="utf-8"))]
    if not rows:
        raise ValueError(f"结果为空：{path}")
    return {(r["scenario"], r["concurrency"], r["repeat"]): r for r in rows}


def fmt(value, digits=2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def main() -> int:
    parser = argparse.ArgumentParser(description="并排比较 API 与本地接口的结果")
    parser.add_argument("api_summary", type=Path)
    parser.add_argument("local_summary", type=Path)
    parser.add_argument("--output", type=Path, default=Path("comparison.md"))
    args = parser.parse_args()
    api = load(args.api_summary)
    local = load(args.local_summary)
    if {r["endpoint"] for r in api.values()} != {"api"} or {r["endpoint"] for r in local.values()} != {"local"}:
        parser.error("第一个文件须为 api，第二个文件须为 local")
    if {r["workload_sha256"] for r in api.values()} != {r["workload_sha256"] for r in local.values()}:
        parser.error("两端负载文件的 SHA256 不一致，不能并排比较")
    keys = sorted(api.keys() & local.keys())
    if not keys:
        parser.error("两份结果没有相同的场景/并发/轮次")
    lines = ["# API 与本地接口性能对比", "",
             f"API：`{next(iter(api.values()))['model']}`；本地：`{next(iter(local.values()))['model']}`。",
             "", "| 场景 | 并发 | 轮次 | 端点 | 成功/请求 | E2E p50 ms | E2E p95 ms | req/s | 服务端输出 token/s | 输入 token 中位数 | 输出 token 中位数 | 可见字符中位数 |",
             "| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    mismatches = []
    if api.keys() != local.keys():
        mismatches.append("两端场景、并发档或轮次不完全一致；表中只展示共同部分")
    for key in keys:
        for label, row in (("API", api[key]), ("本地", local[key])):
            lines.append(f"| {key[0]} | {key[1]} | {key[2]} | {label} | {row['successes']}/{row['requests']} | "
                         f"{fmt(row['e2e_p50_ms'])} | {fmt(row['e2e_p95_ms'])} | "
                         f"{fmt(row['requests_per_second'], 3)} | "
                         f"{fmt(row['server_output_tokens_per_second'], 3)} | "
                         f"{fmt(row.get('server_input_tokens_median'))} | "
                         f"{fmt(row.get('server_output_tokens_median'))} | "
                         f"{fmt(row.get('visible_chars_median'))} |")
        a, b = api[key], local[key]
        if not a.get("prompt_set_sha256") or a.get("prompt_set_sha256") != b.get("prompt_set_sha256"):
            mismatches.append(f"{key}: 两端提示词集合不一致或缺少校验值")
        if a["successes"] < a["requests"] or b["successes"] < b["requests"]:
            mismatches.append(f"{key}: 有失败请求")
        for field in ("server_input_tokens_median", "server_output_tokens_median", "visible_chars_median"):
            x, y = a.get(field), b.get(field)
            if x is None or y is None or min(x, y) == 0 or max(x, y) / min(x, y) > 1.2:
                mismatches.append(f"{key}: {field} 相差超过 20% 或缺失")
    lines += ["", "## 可比性检查", ""]
    if next(iter(api.values()))["model"] != next(iter(local.values()))["model"]:
        mismatches.insert(0, "两端模型名不同，只能解释为两套服务的使用体验比较")
    lines += [f"- {item}" for item in mismatches] if mismatches else ["- 已通过模型名、结果状态及输入/输出长度的基本检查。"]
    lines += ["", "服务端输出 token 可能包含推理 token，不等于可见正文生成速度。若两端 tokenizer 不同，不应比较 token/s 倍数。",
              "单轮小样本的 p95 不稳定；正式结论需要足够样本与多轮结果。", ""]
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
