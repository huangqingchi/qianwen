"""固定题集精度：逐题发送、逐题比答案，一题占一个通过/失败用例。

快速档只有 8 道本地小题；标准档附加 12 道 GSM8K 固定样本，
扩展档附加 20 道。样本很小，分数只是这些题的答对率。
"""

import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from common import call, check


DATA_DIR = Path(__file__).resolve().parents[2]  # 项目根目录，题目保存在这里的 JSON 文件中。


def normalize_answer(value: str) -> str:
    # 本地小题只忽略首尾标点、空格和大小写；其他解释文字仍会导致不匹配。
    return value.strip().strip("。．.，,！! ").replace(" ", "").lower()


def final_number(value: str) -> Decimal | None:
    # GSM8K 优先取“#### 数字”；若模型未遵守格式，则退回取回答中最后一个数字。
    # 退回规则可能误抓无关数字，所以这个分数不等于官方完整基准成绩。
    tagged = re.findall(r"####\s*([-+]?\d[\d,]*(?:\.\d+)?)", value)
    candidates = tagged or re.findall(r"[-+]?\d[\d,]*(?:\.\d+)?", value)
    if not candidates:
        return None
    try:
        return Decimal(candidates[-1].replace(",", ""))
    except InvalidOperation:
        return None


def run(ctx: dict, profile: dict) -> list[dict]:
    # 本地 8 题的题干和标准答案均在 eval_cases.json；每题独立发一次 API 请求。
    cases = json.loads((DATA_DIR / "eval_cases.json").read_text(encoding="utf-8"))
    checks = []
    for case in cases:
        result = call(ctx, [{"role": "user", "content": case["prompt"]}])
        answer = result.get("content", "")
        checks.append(check(case["id"], result.get("status") == 200
                            and normalize_answer(answer) == normalize_answer(case["expected"]),
                            category=case["category"], expected=case["expected"],
                            actual=answer[:200], status_code=result.get("status")))

    # 标准/扩展档读取固定抽样，而非每次随机抽题；便于同条件复测。
    count = profile["gsm8k_cases"]
    if count:
        gsm8k = json.loads((DATA_DIR / "gsm8k_sample.json").read_text(encoding="utf-8"))
        if count > len(gsm8k):
            raise ValueError(f"GSM8K 样本只有 {len(gsm8k)} 道")
        for case in gsm8k[:count]:
            # 要求答案末尾写“#### 数字”，再与参考答案按数值比较。
            prompt = ("Solve this math word problem. Explain briefly, then end your answer "
                      "with a line formatted exactly as #### <number>.\n\n" + case["question"])
            result = call(ctx, [{"role": "user", "content": prompt}])
            actual = final_number(result.get("content", ""))
            expected = final_number(case["expected"])
            checks.append(check(f"GSM8K #{case['source_index']}",
                                result.get("status") == 200 and actual is not None
                                and actual == expected,
                                expected=case["expected"],
                                actual=None if actual is None else str(actual),
                                status_code=result.get("status")))
    return checks
