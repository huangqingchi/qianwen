"""Create chart-focused PDF reports from saved benchmark results."""

from __future__ import annotations

import argparse
import json
import os
import statistics
from collections import defaultdict
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from result_fields import FIELDS, english_summary


PAGE_W, PAGE_H = landscape(A4)
BLUE = colors.HexColor("#2563EB")
TEAL = colors.HexColor("#0D9488")
ORANGE = colors.HexColor("#EA580C")
RED = colors.HexColor("#DC2626")
INK = colors.HexColor("#172033")
MUTED = colors.HexColor("#64748B")
GRID = colors.HexColor("#E2E8F0")
PALE = colors.HexColor("#F4F7FB")
SERIES_COLORS = {"short": BLUE, "medium": TEAL, "long": ORANGE}
SCENE_NAMES = {"short": "短输入", "medium": "中输入", "long": "长输入"}


def register_font() -> str:
    candidates = (
        Path(os.environ["QIANWEN_PDF_FONT"]) if os.environ.get("QIANWEN_PDF_FONT") else None,
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/arphic/ukai.ttc"),
    )
    for path in candidates:
        if path is not None and path.is_file():
            try:
                pdfmetrics.registerFont(TTFont("ReportChinese", str(path)))
                return "ReportChinese"
            except Exception:
                continue
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light"


def label(pdf: canvas.Canvas, x: float, y: float, value: str, font: str,
          size: float = 9, color=INK) -> None:
    pdf.setFillColor(color)
    pdf.setFont(font, size)
    pdf.drawString(x, y, str(value))


def fit(value: object, max_chars: int = 76) -> str:
    text = str(value)
    return text if len(text) <= max_chars else text[:max_chars - 1] + "…"


def box(pdf: canvas.Canvas, x: float, y: float, w: float, h: float,
        fill=colors.white, stroke=GRID, radius: float = 9) -> None:
    pdf.setFillColor(fill)
    pdf.setStrokeColor(stroke)
    pdf.roundRect(x, y, w, h, radius, stroke=1, fill=1)


def page_header(pdf: canvas.Canvas, font: str, title: str, subtitle: str, page: int) -> None:
    pdf.setFillColor(PALE)
    pdf.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
    label(pdf, 34, PAGE_H - 40, title, font, 21)
    label(pdf, 35, PAGE_H - 60, fit(subtitle, 115), font, 8.7, MUTED)
    label(pdf, PAGE_W - 66, 20, f"{page}", font, 8, MUTED)


def metric_card(pdf: canvas.Canvas, font: str, x: float, y: float, w: float,
                title: str, value: str, note: str = "") -> None:
    box(pdf, x, y, w, 68)
    label(pdf, x + 13, y + 47, title, font, 8.5, MUTED)
    label(pdf, x + 13, y + 21, value, font, 18, INK)
    if note:
        pdf.setFont(font, 7.5)
        pdf.setFillColor(MUTED)
        pdf.drawRightString(x + w - 11, y + 23, note)


def grouped(rows: list[dict], field: str, percent: bool = False) -> dict[str, dict[int, float]]:
    buckets: dict[tuple[str, int], list[float]] = defaultdict(list)
    for row in rows:
        value = row.get(field)
        if isinstance(value, (int, float)):
            buckets[(row["scenario"], row["concurrency"])].append(float(value) * (100 if percent else 1))
    result: dict[str, dict[int, float]] = defaultdict(dict)
    for (scene, concurrency), values in buckets.items():
        result[scene][concurrency] = statistics.median(values)
    return result


def draw_chart(pdf: canvas.Canvas, font: str, x: float, y: float, w: float, h: float,
               title: str, data: dict[str, dict[int, float]], unit: str,
               all_levels: list[int], percent: bool = False,
               secondary: dict[str, dict[int, float]] | None = None) -> None:
    box(pdf, x, y, w, h)
    label(pdf, x + 14, y + h - 24, title, font, 11)
    if not any(data.values()):
        label(pdf, x + 18, y + h / 2, "暂无可用样本", font, 10, MUTED)
        return
    left, right = x + 44, x + w - 18
    bottom, top = y + 36, y + h - 55
    values_for_scale = [value for series in data.values() for value in series.values()]
    if secondary:
        values_for_scale.extend(value for series in secondary.values() for value in series.values())
    max_value = max(values_for_scale)
    if percent and max_value == 0:
        label(pdf, x + 18, y + h / 2, "全部场景和并发档均为 0% 失败", font, 12, TEAL)
        label(pdf, x + 18, y + h / 2 - 21, "各档请求数见同目录 summary.json。", font, 8, MUTED)
        return
    ceiling = 100.0 if percent else max(max_value * 1.16, 1.0)
    pdf.setStrokeColor(GRID)
    pdf.setLineWidth(0.7)
    for tick in range(5):
        yy = bottom + (top - bottom) * tick / 4
        pdf.line(left, yy, right, yy)
        pdf.setFont(font, 7)
        pdf.setFillColor(MUTED)
        tick_value = ceiling * tick / 4
        tick_text = f"{tick_value:.2f}" if ceiling < 1 else f"{tick_value:.1f}" if ceiling < 10 else f"{tick_value:.0f}"
        pdf.drawRightString(left - 6, yy - 2, tick_text)
    levels = sorted(all_levels)
    x_at = lambda c: left + (right - left) * (levels.index(c) + 0.5) / len(levels)
    for c in levels:
        pdf.setFont(font, 7.5)
        pdf.setFillColor(MUTED)
        pdf.drawCentredString(x_at(c), bottom - 15, str(c))
    for scene, color in SERIES_COLORS.items():
        values = data.get(scene, {})
        if not values:
            continue
        pdf.setStrokeColor(color)
        pdf.setFillColor(color)
        pdf.setLineWidth(1.8)
        points = [(x_at(c), bottom + (top - bottom) * values[c] / ceiling)
                  for c in levels if c in values]
        if secondary:
            for c in levels:
                other = secondary.get(scene, {}).get(c)
                if c not in values or other is None:
                    continue
                xx = x_at(c)
                first_y = bottom + (top - bottom) * values[c] / ceiling
                other_y = bottom + (top - bottom) * other / ceiling
                pdf.setStrokeColor(color)
                pdf.setLineWidth(1)
                pdf.line(xx, first_y, xx, other_y)
                pdf.setFillColor(colors.white)
                pdf.circle(xx, other_y, 3.4, fill=1, stroke=1)
        for one, two in zip(points, points[1:]):
            pdf.line(*one, *two)
        pdf.setFillColor(color)
        for px, py in points:
            pdf.circle(px, py, 3.4, fill=1, stroke=0)
        legend_x = x + w - 176 + 56 * list(SERIES_COLORS).index(scene)
        pdf.circle(legend_x, y + h - 42, 3, fill=1, stroke=0)
        label(pdf, legend_x + 7, y + h - 45, SCENE_NAMES[scene], font, 7.5, MUTED)
    caption = (f"并发数 · {unit} · 各轮中位数 · 实心 P50 / 空心 P95" if secondary is not None
               else f"并发数  ·  {unit}  ·  各轮中位数")
    label(pdf, left, y + 10, caption, font, 7.2, MUTED)


def draw_overview(pdf: canvas.Canvas, font: str, rows: list[dict], meta: dict) -> None:
    first = rows[0]
    profile = meta.get("测试档位", meta.get("profile", "未知"))
    subtitle = f"{first['model']}  ·  {first['endpoint']}  ·  {profile}  ·  {meta.get('开始时间UTC', meta.get('started_utc', ''))}"
    page_header(pdf, font, "API 接口性能测试", subtitle, 1)
    total = sum(r["requests"] for r in rows)
    successes = sum(r["successes"] for r in rows)
    errors = total - successes
    scenes = {r["scenario"] for r in rows}
    levels = sorted({r["concurrency"] for r in rows})
    repeats = {r["repeat"] for r in rows}
    card_w = (PAGE_W - 68 - 3 * 12) / 4
    metric_card(pdf, font, 34, PAGE_H - 146, card_w, "采集请求", str(total), f"{len(rows)} 组")
    metric_card(pdf, font, 46 + card_w, PAGE_H - 146, card_w,
                "成功请求", str(successes), f"失败 {errors}")
    metric_card(pdf, font, 58 + card_w * 2, PAGE_H - 146, card_w,
                "输入长度场景", str(len(scenes)), "分场景展示")
    metric_card(pdf, font, 70 + card_w * 3, PAGE_H - 146, card_w,
                "并发档位", str(len(levels)), f"重复 {len(repeats)} 轮")
    panel_w = (PAGE_W - 68 - 14) / 2
    draw_chart(pdf, font, 34, 251, panel_w, 177, "端到端延迟 P50 / P95",
               grouped(rows, "e2e_p50_ms"), "ms", levels,
               secondary=grouped(rows, "e2e_p95_ms"))
    draw_chart(pdf, font, 48 + panel_w, 251, panel_w, 177, "成功请求吞吐", grouped(rows, "requests_per_second"), "req/s", levels)
    draw_chart(pdf, font, 34, 52, panel_w, 177, "失败率", grouped(rows, "error_rate", True), "%", levels, True)
    draw_chart(pdf, font, 48 + panel_w, 52, panel_w, 177, "服务端输出吞吐", grouped(rows, "server_output_tokens_per_second"), "token/s", levels)
    note = "各场景分别作图；不跨输入长度合并延迟或吞吐。点为相同场景、并发下的轮次中位数。"
    label(pdf, 35, 33, note, font, 8, MUTED)
    pdf.showPage()


def draw_scene_page(pdf: canvas.Canvas, font: str, scene: str,
                    rows: list[dict], page_number: int) -> None:
    scene_rows = [row for row in rows if row["scenario"] == scene]
    if not scene_rows:
        return
    first = scene_rows[0]
    total = sum(row["requests"] for row in scene_rows)
    successes = sum(row["successes"] for row in scene_rows)
    levels = sorted({row["concurrency"] for row in scene_rows})
    token_values = [row["server_output_tokens_median"] for row in scene_rows
                    if row.get("server_output_tokens_median") is not None]
    visible_values = [row["visible_chars_median"] for row in scene_rows
                      if row.get("visible_chars_median") is not None]
    page_header(pdf, font, f"{SCENE_NAMES.get(scene, scene)} · 并发扫描",
                f"{first['model']}  ·  并发 {' / '.join(map(str, levels))}  ·  各档按自己的长度与时间尺度显示", page_number)
    card_w = (PAGE_W - 68 - 3 * 12) / 4
    metric_card(pdf, font, 34, PAGE_H - 146, card_w, "本场景请求", str(total),
                f"{len(levels)} 档 / {len({row['repeat'] for row in scene_rows})} 轮")
    metric_card(pdf, font, 46 + card_w, PAGE_H - 146, card_w,
                "成功请求", str(successes), f"失败 {total - successes}")
    metric_card(pdf, font, 58 + card_w * 2, PAGE_H - 146, card_w,
                "输出 token 中位数范围",
                f"{min(token_values):.0f}–{max(token_values):.0f}" if token_values else "—")
    metric_card(pdf, font, 70 + card_w * 3, PAGE_H - 146, card_w,
                "可见字符中位数范围",
                f"{min(visible_values):.0f}–{max(visible_values):.0f}" if visible_values else "—")
    panel_w = (PAGE_W - 68 - 14) / 2
    draw_chart(pdf, font, 34, 251, panel_w, 177, "端到端延迟 P50 / P95",
               grouped(scene_rows, "e2e_p50_ms"), "ms", levels,
               secondary=grouped(scene_rows, "e2e_p95_ms"))
    draw_chart(pdf, font, 48 + panel_w, 251, panel_w, 177,
               "成功请求吞吐", grouped(scene_rows, "requests_per_second"), "req/s", levels)
    draw_chart(pdf, font, 34, 52, panel_w, 177,
               "首生成事件 P50", grouped(scene_rows, "first_generated_event_p50_ms"), "ms", levels)
    draw_chart(pdf, font, 48 + panel_w, 52, panel_w, 177,
               "首段可见文本 P50", grouped(scene_rows, "first_visible_text_p50_ms"), "ms", levels)
    label(pdf, 35, 33, "图中各点为同并发档多轮结果的中位数；P95 缺点表示该轮成功样本不足 100 条。", font, 8, MUTED)
    pdf.showPage()


def request_value(row: dict, key: str):
    return row.get(FIELDS[key], row.get(key))


def value_at(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * fraction
    low = int(index)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def distribution_bounds(values: list[float]) -> tuple[float, float, int]:
    low = min(values) * 0.95
    high = min(max(values), max(value_at(values, 0.95) * 1.5,
                                 value_at(values, 0.99)))
    if high <= low:
        high = low + max(abs(low) * 0.1, 1)
    return low, high, sum(value > high for value in values)


def draw_histogram(pdf: canvas.Canvas, font: str, x: float, y: float,
                   w: float, h: float, values: list[float]) -> None:
    box(pdf, x, y, w, h)
    label(pdf, x + 14, y + h - 24, "端到端耗时分布", font, 11)
    if not values:
        label(pdf, x + 18, y + h / 2, "没有成功请求", font, 10, MUTED)
        return
    left, right, bottom, top = x + 42, x + w - 17, y + 37, y + h - 56
    low, high, overflow = distribution_bounds(values)
    bins = 9
    counts = [0] * bins
    for value in values:
        if value <= high:
            counts[min(int((value - low) / (high - low) * bins), bins - 1)] += 1
    regular_right = right - 39 if overflow else right
    bar_w = (regular_right - left) / bins
    pdf.setFillColor(BLUE)
    for index, count in enumerate(counts):
        height = (top - bottom) * count / max(counts)
        pdf.rect(left + index * bar_w + 1, bottom, bar_w - 2, height, fill=1, stroke=0)
    if overflow:
        pdf.setFillColor(ORANGE)
        pdf.rect(right - 27, bottom, 23, (top - bottom) * overflow / max(counts), fill=1, stroke=0)
    for fraction, color, name in ((0.5, ORANGE, "P50"), (0.95, RED, "P95")):
        marker = value_at(values, fraction)
        xx = left + (regular_right - left) * (marker - low) / (high - low)
        pdf.setStrokeColor(color)
        pdf.setLineWidth(1.5)
        pdf.line(xx, bottom, xx, top)
        label(pdf, x + (14 if fraction == 0.5 else 125), y + h - 42,
              f"{name} {marker:.0f} ms", font, 7.5, color)
    label(pdf, left, y + 12, f"{low:.0f} ms", font, 7, MUTED)
    pdf.setFont(font, 7)
    pdf.setFillColor(MUTED)
    pdf.drawRightString(regular_right, y + 12, f"{high:.0f} ms")
    if overflow:
        label(pdf, right - 34, y + 12, f"> {high:.0f}", font, 6.5, MUTED)
    label(pdf, right - 99, y + h - 42,
          f"n={len(values)}；尾部 {overflow} 条" if overflow else f"n={len(values)}", font, 7.5, MUTED)


def draw_cdf(pdf: canvas.Canvas, font: str, x: float, y: float,
             w: float, h: float, values: list[float]) -> None:
    box(pdf, x, y, w, h)
    label(pdf, x + 14, y + h - 24, "端到端耗时累计分布", font, 11)
    if not values:
        label(pdf, x + 18, y + h / 2, "没有成功请求", font, 10, MUTED)
        return
    ordered = sorted(values)
    left, right, bottom, top = x + 42, x + w - 18, y + 37, y + h - 49
    low, high, overflow = distribution_bounds(values)
    pdf.setStrokeColor(GRID)
    pdf.setLineWidth(0.7)
    for fraction in (0, 0.5, 1):
        yy = bottom + (top - bottom) * fraction
        pdf.line(left, yy, right, yy)
        pdf.setFont(font, 7)
        pdf.setFillColor(MUTED)
        pdf.drawRightString(left - 5, yy - 2, f"{fraction * 100:.0f}%")
    path = pdf.beginPath()
    path.moveTo(left + (right - left) * (ordered[0] - low) / (high - low), bottom)
    for index, value in enumerate(ordered, 1):
        if value > high:
            break
        path.lineTo(left + (right - left) * (value - low) / (high - low),
                    bottom + (top - bottom) * index / len(ordered))
    pdf.setStrokeColor(TEAL)
    pdf.setLineWidth(1.8)
    pdf.drawPath(path, stroke=1, fill=0)
    for fraction, color in ((0.5, ORANGE), (0.95, RED)):
        xx = left + (right - left) * (value_at(values, fraction) - low) / (high - low)
        pdf.setStrokeColor(color)
        pdf.setDash(2, 2)
        pdf.setLineWidth(0.9)
        pdf.line(xx, bottom, xx, bottom + (top - bottom) * fraction)
    pdf.setDash()
    label(pdf, left, y + 12, f"{low:.0f} ms", font, 7, MUTED)
    pdf.setFont(font, 7)
    pdf.setFillColor(MUTED)
    pdf.drawRightString(right, y + 12, f"{high:.0f} ms")
    if overflow:
        label(pdf, x + 143, y + h - 24,
              f"{overflow} 条超出横轴；最大 {max(values):.0f} ms", font, 7.3, ORANGE)


def draw_request_order(pdf: canvas.Canvas, font: str, x: float, y: float,
                       w: float, h: float, requests: list[dict]) -> None:
    box(pdf, x, y, w, h)
    label(pdf, x + 14, y + h - 24, "按请求序号查看端到端耗时", font, 11)
    points = [(request_value(row, "request_index"), request_value(row, "end_to_end_latency_s"),
               request_value(row, "error_code")) for row in requests]
    points = [(index, elapsed * 1000, error) for index, elapsed, error in points
              if isinstance(index, int) and isinstance(elapsed, (int, float))]
    if not points:
        label(pdf, x + 18, y + h / 2, "没有可用耗时记录", font, 10, MUTED)
        return
    left, right, bottom, top = x + 42, x + w - 18, y + 37, y + h - 48
    ceiling = max(value for _, value, _ in points) * 1.08 or 1
    max_index = max(index for index, _, _ in points) or 1
    for fraction in (0, 0.5, 1):
        yy = bottom + (top - bottom) * fraction
        pdf.setStrokeColor(GRID)
        pdf.line(left, yy, right, yy)
        pdf.setFont(font, 7)
        pdf.setFillColor(MUTED)
        pdf.drawRightString(left - 5, yy - 2, f"{ceiling * fraction:.0f}")
    for index, elapsed, error in points:
        pdf.setFillColor(RED if error else BLUE)
        pdf.circle(left + (right - left) * index / max_index,
                   bottom + (top - bottom) * elapsed / ceiling, 2.1, fill=1, stroke=0)
    successful = [elapsed for _, elapsed, error in points if error is None]
    if successful:
        p95 = value_at(successful, 0.95)
        yy = bottom + (top - bottom) * p95 / ceiling
        pdf.setStrokeColor(RED)
        pdf.setDash(2, 2)
        pdf.line(left, yy, right, yy)
        pdf.setDash()
        label(pdf, right - 55, yy + 4, f"P95 {p95:.0f}", font, 7, RED)
    label(pdf, left, y + 12, "第 1 条", font, 7, MUTED)
    pdf.setFont(font, 7)
    pdf.setFillColor(MUTED)
    pdf.drawRightString(right, y + 12, f"第 {max_index + 1} 条")


def draw_generation_times(pdf: canvas.Canvas, font: str, x: float, y: float,
                          w: float, h: float, requests: list[dict]) -> None:
    box(pdf, x, y, w, h)
    label(pdf, x + 14, y + h - 24, "生成事件与可见文本", font, 11)
    series = [
        ("首生成事件", [request_value(row, "first_generated_event_ms") for row in requests], TEAL),
        ("首段可见文本", [request_value(row, "first_visible_text_ms") for row in requests], ORANGE),
    ]
    series = [(name, [float(v) for v in values if isinstance(v, (int, float))], color)
              for name, values, color in series]
    nonempty = [values for _, values, _ in series if values]
    if not nonempty:
        label(pdf, x + 18, y + h / 2, "没有生成时间记录", font, 10, MUTED)
        return
    left, right = x + 115, x + w - 23
    ceiling = max(value_at(values, 0.95) for values in nonempty) * 1.12 or 1
    for offset, (name, values, color) in enumerate(series):
        yy = y + 91 - offset * 43
        label(pdf, x + 16, yy + 3, name, font, 8, MUTED)
        pdf.setFillColor(GRID)
        pdf.roundRect(left, yy, right - left, 14, 3, fill=1, stroke=0)
        if values:
            p50 = value_at(values, 0.5)
            p95 = value_at(values, 0.95)
            pdf.setFillColor(color)
            pdf.rect(left, yy, (right - left) * min(p50 / ceiling, 1), 14, fill=1, stroke=0)
            pdf.setStrokeColor(color)
            pdf.setLineWidth(1.5)
            xx = left + (right - left) * min(p95 / ceiling, 1)
            pdf.line(xx, yy - 3, xx, yy + 17)
            label(pdf, left, yy - 13, f"P50 {p50:.0f} ms  ·  P95 {p95:.0f} ms  ·  n={len(values)}", font, 7, MUTED)
    label(pdf, x + 16, y + 13, "实色条为 P50；细线为 P95。首生成事件可包含推理内容。", font, 7.5, MUTED)


def draw_fixed_concurrency(pdf: canvas.Canvas, font: str, summary: dict,
                           meta: dict, requests: list[dict]) -> None:
    scene = SCENE_NAMES.get(summary["scenario"], summary["scenario"])
    page_header(pdf, font, f"并发 {summary['concurrency']} · 多请求实测",
                f"{summary['model']}  ·  {scene}  ·  {meta.get('开始时间UTC', meta.get('started_utc', ''))}", 1)
    card_w = (PAGE_W - 68 - 3 * 12) / 4
    metric_card(pdf, font, 34, PAGE_H - 146, card_w, "采集请求", str(summary["requests"]),
                f"成功 {summary['successes']}")
    metric_card(pdf, font, 46 + card_w, PAGE_H - 146, card_w, "端到端 P50",
                f"{summary['e2e_p50_ms']:.0f} ms" if summary.get("e2e_p50_ms") is not None else "—")
    metric_card(pdf, font, 58 + card_w * 2, PAGE_H - 146, card_w, "端到端 P95",
                f"{summary['e2e_p95_ms']:.0f} ms" if summary.get("e2e_p95_ms") is not None else "—")
    metric_card(pdf, font, 70 + card_w * 3, PAGE_H - 146, card_w, "成功请求吞吐",
                f"{summary['requests_per_second']:.2f} req/s", f"失败 {summary['errors']}")
    values = [request_value(row, "end_to_end_latency_s") * 1000 for row in requests
              if request_value(row, "error_code") is None and
              isinstance(request_value(row, "end_to_end_latency_s"), (int, float))]
    panel_w = (PAGE_W - 68 - 14) / 2
    draw_histogram(pdf, font, 34, 251, panel_w, 177, values)
    draw_cdf(pdf, font, 48 + panel_w, 251, panel_w, 177, values)
    draw_request_order(pdf, font, 34, 52, panel_w, 177, requests)
    draw_generation_times(pdf, font, 48 + panel_w, 52, panel_w, 177, requests)
    label(pdf, 35, 33,
          f"输出 token 中位数 {summary.get('server_output_tokens_median') or '—'}；"
          f"可见字符中位数 {summary.get('visible_chars_median') or '—'}。"
          "服务端输出 token 可能包含推理 token。", font, 8, MUTED)
    pdf.showPage()


def draw_smoke(pdf: canvas.Canvas, font: str, rows: list[dict], meta: dict,
               directory: Path) -> None:
    summary = rows[0]
    request_path = directory / summary["request_file"]
    request = None
    if request_path.is_file():
        lines = request_path.read_text(encoding="utf-8").splitlines()
        if lines:
            request = json.loads(lines[0])
    request = request or {}
    subtitle = f"{summary['model']}  ·  {summary['endpoint']}  ·  {meta.get('开始时间UTC', meta.get('started_utc', ''))}"
    page_header(pdf, font, "接口连通性检查", subtitle, 1)
    box(pdf, 34, 488, PAGE_W - 68, 30, colors.HexColor("#FFF7ED"), colors.HexColor("#FDBA74"), 7)
    label(pdf, 45, 499, "本次仅采集 1 条请求。下方是单次观测值，不代表延迟分位数、稳定吞吐或服务成功率。", font, 9, ORANGE)

    elapsed = request_value(request, "end_to_end_latency_s")
    first_event = request_value(request, "first_generated_event_ms")
    first_visible = request_value(request, "first_visible_text_ms")
    status = request_value(request, "http_status")
    done = request_value(request, "done")
    error = request_value(request, "error_code")
    chars = request_value(request, "visible_chars")
    card_w = (PAGE_W - 68 - 3 * 12) / 4
    request_succeeded = summary["successes"] > 0 and error is None
    metric_card(pdf, font, 34, 408, card_w, "请求状态", "成功" if request_succeeded else "失败",
                f"HTTP {status}" if status is not None else "无状态码")
    metric_card(pdf, font, 46 + card_w, 408, card_w, "本次端到端耗时",
                f"{elapsed * 1000:.0f} ms" if isinstance(elapsed, (int, float)) else "—")
    metric_card(pdf, font, 58 + card_w * 2, 408, card_w, "首段可见文本",
                f"{first_visible:.0f} ms" if isinstance(first_visible, (int, float)) else "—")
    metric_card(pdf, font, 70 + card_w * 3, 408, card_w, "可见文本长度",
                f"{chars} 字符" if chars is not None else "—")

    x, y, w, h = 34, 211, PAGE_W - 68, 177
    box(pdf, x, y, w, h)
    label(pdf, x + 16, y + h - 26, "单次请求时间线", font, 11)
    left, right, line_y = x + 61, x + w - 49, y + 88
    total_ms = max(elapsed * 1000, 1) if isinstance(elapsed, (int, float)) else 1
    pdf.setStrokeColor(GRID)
    pdf.setLineWidth(5)
    pdf.line(left, line_y, right, line_y)
    pdf.setStrokeColor(BLUE)
    pdf.setLineWidth(5)
    pdf.line(left, line_y, right, line_y)
    for fraction in (0, 0.25, 0.5, 0.75, 1):
        xx = left + (right - left) * fraction
        pdf.setStrokeColor(colors.white)
        pdf.setLineWidth(1)
        pdf.line(xx, line_y - 5, xx, line_y + 5)
        pdf.setFont(font, 7.3)
        pdf.setFillColor(MUTED)
        pdf.drawCentredString(xx, line_y - 24, f"{total_ms * fraction:.0f} ms")
    milestones = [
        ("发出请求", 0, INK),
        ("首生成事件", first_event, TEAL),
        ("首段可见文本", first_visible, ORANGE),
        ("收到完整响应" if done else "响应结束", total_ms, BLUE),
    ]
    for _, value, color in milestones:
        if isinstance(value, (int, float)):
            xx = left + (right - left) * min(max(value / total_ms, 0), 1)
            pdf.setFillColor(color)
            pdf.circle(xx, line_y, 5, fill=1, stroke=0)
    legend_y = y + 31
    for index, (name, value, color) in enumerate(milestones):
        xx = x + 24 + index * 185
        pdf.setFillColor(color)
        pdf.circle(xx, legend_y, 3.5, fill=1, stroke=0)
        value_text = f"{value:.0f} ms" if isinstance(value, (int, float)) else "未记录"
        label(pdf, xx + 9, legend_y - 3, f"{name}  {value_text}", font, 8, MUTED)

    x, y, w, h = 34, 35, PAGE_W - 68, 158
    box(pdf, x, y, w, h)
    label(pdf, x + 16, y + h - 25, "本次 token 用量", font, 11)
    usage = request_value(request, "usage") or {}
    input_tokens = request_value(request, "number_input_tokens")
    output_tokens = request_value(request, "number_output_tokens")
    detail = usage.get(FIELDS["completion_tokens_details"], usage.get("completion_tokens_details")) or {}
    reasoning = detail.get(FIELDS["reasoning_tokens"], detail.get("reasoning_tokens"))
    input_tokens = input_tokens if type(input_tokens) is int else summary.get("server_input_tokens_median") or 0
    output_tokens = output_tokens if type(output_tokens) is int else summary.get("server_output_tokens_median") or 0
    reasoning = reasoning if type(reasoning) is int else 0
    scale = max(input_tokens, output_tokens, 1)
    bar_x, bar_w = x + 139, w - 235
    for bar_y, title, count, color in ((y + 91, "输入 token", input_tokens, TEAL),
                                      (y + 52, "输出 token", output_tokens, BLUE)):
        label(pdf, x + 18, bar_y + 5, title, font, 8.7, MUTED)
        pdf.setFillColor(GRID)
        pdf.roundRect(bar_x, bar_y, bar_w, 18, 4, fill=1, stroke=0)
        pdf.setFillColor(color)
        pdf.roundRect(bar_x, bar_y, bar_w * count / scale, 18, 4, fill=1, stroke=0)
        label(pdf, bar_x + bar_w + 11, bar_y + 5, str(count) if count else "未提供", font, 8.7)
    if output_tokens and reasoning:
        pdf.setFillColor(ORANGE)
        pdf.rect(bar_x, y + 52, bar_w * min(reasoning, output_tokens) / scale, 18, fill=1, stroke=0)
    label(pdf, x + 18, y + 16,
          f"橙色为推理 token：{reasoning if reasoning else '未提供'}；输出 token 包含推理部分，不能等同可见正文速度。",
          font, 8, MUTED)
    pdf.showPage()


def build_pdf(directory: Path) -> Path:
    directory = directory.resolve()
    summary = directory / "summary.json"
    if not summary.is_file():
        raise FileNotFoundError(f"找不到汇总结果：{summary}")
    rows = [english_summary(row) for row in json.loads(summary.read_text(encoding="utf-8-sig"))]
    if not rows:
        raise ValueError("汇总结果为空")
    metadata = directory / "metadata.json"
    meta = json.loads(metadata.read_text(encoding="utf-8-sig")) if metadata.is_file() else {}
    font = register_font()
    output = directory / "性能报告.pdf"
    pdf = canvas.Canvas(str(output), pagesize=(PAGE_W, PAGE_H), pageCompression=1)
    pdf.setTitle("API 接口性能测试报告")
    pdf.setAuthor("qianwen benchmark")
    profile = meta.get("测试档位", meta.get("profile"))
    if profile == "smoke":
        draw_smoke(pdf, font, rows, meta, directory)
    elif len(rows) == 1 and rows[0]["requests"] > 1:
        request_path = directory / rows[0]["request_file"]
        if not request_path.is_file():
            raise FileNotFoundError(f"找不到逐请求记录：{request_path}")
        requests = [json.loads(line) for line in request_path.read_text(encoding="utf-8").splitlines() if line]
        draw_fixed_concurrency(pdf, font, rows[0], meta, requests)
    else:
        draw_overview(pdf, font, rows, meta)
        for index, scene in enumerate(("short", "medium", "long"), 2):
            draw_scene_page(pdf, font, scene, rows, index)
    pdf.save()
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="由已有 JSON 结果生成图表 PDF，不请求模型")
    parser.add_argument("result_dir", type=Path)
    args = parser.parse_args()
    print(build_pdf(args.result_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
