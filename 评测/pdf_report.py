"""把一次运行中各项目的结果.json 汇总为一份中文 PDF。"""

from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ITEMS = ("接口契约", "错误契约", "用量统计", "长上下文", "缓存命中", "固定题集精度", "性能基线")
FONT = "STSong-Light"


def display(value: object) -> str:
    if value is True:
        return "是"
    if value is False:
        return "否"
    if value is None:
        return "未提供"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def read_results(run_dir: Path) -> list[dict]:
    results = []
    for item in ITEMS:
        path = run_dir / item / "结果.json"
        if path.is_file():
            result = json.loads(path.read_text(encoding="utf-8"))
            if result.get("项目") != item:
                raise ValueError(f"结果项目名称与目录不一致：{path}")
            results.append(result)
    if not results:
        raise ValueError(f"找不到任何项目的结果.json：{run_dir}")
    models = {result.get("模型") for result in results}
    profiles = {result.get("测试档位") for result in results}
    if len(models) != 1 or len(profiles) != 1:
        raise ValueError("同一份 PDF 的模型和测试档位必须一致")
    return results


def build_pdf(run_dir: Path) -> Path:
    """只读取已保存的 JSON，不发送 API 请求；保留原有报告和 JSON。"""
    run_dir = run_dir.resolve()
    results = read_results(run_dir)
    pdfmetrics.registerFont(UnicodeCIDFont(FONT))
    output = run_dir / "评测汇总.pdf"
    styles = {
        "title": ParagraphStyle("标题", fontName=FONT, fontSize=19, leading=28,
                                alignment=TA_CENTER, spaceAfter=13),
        "h1": ParagraphStyle("一级标题", fontName=FONT, fontSize=13, leading=20,
                             spaceBefore=15, spaceAfter=7),
        "h2": ParagraphStyle("二级标题", fontName=FONT, fontSize=10.5, leading=16,
                             spaceBefore=9, spaceAfter=3),
        "body": ParagraphStyle("正文", fontName=FONT, fontSize=9, leading=15,
                               wordWrap="CJK", spaceAfter=4),
        "small": ParagraphStyle("表格", fontName=FONT, fontSize=8, leading=12,
                                wordWrap="CJK"),
    }

    def paragraph(value: object, style: str = "body") -> Paragraph:
        return Paragraph(escape(display(value)), styles[style])

    story = [paragraph("模型评测汇总", "title")]
    first = results[0]
    story.append(paragraph(f"模型：{first['模型']}　测试档位：{first['测试档位']}"))
    story.append(paragraph(f"测试时间（UTC）：{first.get('测试时间（UTC）', '未提供')}"))
    story.append(paragraph(f"结果目录：{run_dir.name}　已汇总项目：{len(results)} 项"))
    story.append(paragraph("分数是本地用例通过率；未评分项目只展示测量值，不代表正式等级。"))

    story.append(paragraph("一、项目总览", "h1"))
    rows = [[paragraph(label, "small") for label in
             ("项目", "分数", "通过", "失败", "待确认", "仅测量")]]
    for result in results:
        tally = result["计分"]
        value = tally["本地用例分数"]
        score = f"{value:g} 分" if isinstance(value, (int, float)) else "未评分"
        rows.append([paragraph(v, "small") for v in (
            result["项目"], score, tally["通过数"], tally["失败数"],
            tally["待确认数"], tally["仅测量数"],
        )])
    table = Table(rows, colWidths=[48*mm, 33*mm, 19*mm, 19*mm, 23*mm, 23*mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E7EEF5")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend((table, Spacer(1, 5*mm)))

    story.append(paragraph("二、逐项结果", "h1"))
    for result in results:
        tally = result["计分"]
        score = tally["本地用例分数"]
        score_text = f"{score:g} 分" if isinstance(score, (int, float)) else "未评分"
        story.append(paragraph(f"{result['项目']}　{score_text}", "h1"))
        story.append(paragraph(
            f"通过 {tally['通过数']} 项；失败 {tally['失败数']} 项；"
            f"待确认 {tally['待确认数']} 项；仅测量 {tally['仅测量数']} 项。"
        ))
        for case in result.get("用例结果", []):
            details = [f"{key}：{display(value)}" for key, value in case.items()
                       if key not in {"用例名称", "结果"}]
            block = [paragraph(f"{case.get('用例名称', '未命名用例')}　—　{case.get('结果', '未知')}", "h2")]
            block.extend(paragraph(detail) for detail in details)
            story.append(KeepTogether(block))
        calls = result.get("请求记录", [])
        if calls:
            success = sum(call.get("HTTP状态码") == 200 for call in calls)
            story.append(paragraph(f"请求记录：{len(calls)} 次，其中 HTTP 200 为 {success} 次。", "small"))

    story.append(paragraph("三、判读说明", "h1"))
    story.append(paragraph("各项分数按通过数 ÷（通过数＋失败数）计算；待确认和仅测量不计入分母。"))
    story.append(paragraph("性能基线当前没有等级阈值，P50/P95 来自少量请求，仅供观察。固定题集也只是已测样本。"))

    doc = SimpleDocTemplate(str(output), pagesize=A4, leftMargin=22*mm,
                            rightMargin=22*mm, topMargin=20*mm, bottomMargin=19*mm,
                            title="模型评测汇总", author="qianwen 评测")

    def page_number(canvas, document):
        canvas.setFont(FONT, 8)
        canvas.drawRightString(A4[0] - 22*mm, 12*mm, f"第 {document.page} 页")

    doc.build(story, onFirstPage=page_number, onLaterPages=page_number)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="把已有评测结果汇总为 PDF，不调用模型")
    parser.add_argument("run_dir", type=Path, help="某次运行的结果目录")
    args = parser.parse_args()
    run_dir = args.run_dir if args.run_dir.is_absolute() else PROJECT_ROOT / args.run_dir
    try:
        output = build_pdf(run_dir)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(f"PDF：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
