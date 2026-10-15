"""Convert existing benchmark result keys to Chinese without calling an API."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from result_fields import chinese


def convert_directory(directory: Path) -> None:
    for name in ("metadata.json", "summary.json"):
        path = directory / name
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            path.write_text(json.dumps(chinese(data), ensure_ascii=False, indent=2), encoding="utf-8")
    for path in directory.glob("*.jsonl"):
        rows = [chinese(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line]
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = directory / "summary.json"
    if summary.is_file():
        rows = json.loads(summary.read_text(encoding="utf-8"))
        if rows:
            with (directory / "summary.csv").open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="把已有性能结果的键转换为中文")
    parser.add_argument("directories", nargs="+", type=Path)
    args = parser.parse_args()
    for directory in args.directories:
        if not directory.is_dir():
            parser.error(f"结果目录不存在：{directory}")
        convert_directory(directory)
        print(directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
