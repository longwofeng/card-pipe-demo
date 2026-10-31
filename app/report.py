"""报告与清单输出，以及两次报告的 diff。"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .models import Report

REPORT_FILE = "report.json"
MANIFEST_FILE = "manifest.csv"
PDF_FILE = "batch.pdf"


def report_dict(report: Report) -> dict:
    """固定字段顺序（pydantic 按声明顺序 dump）。"""
    return report.model_dump()


def write_report(report: Report, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / REPORT_FILE
    path.write_text(json.dumps(report_dict(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def write_manifest(report: Report, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    path = out_dir / MANIFEST_FILE
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "output", "status", "issues"])
        for item in report.items:
            writer.writerow([item.id, f"{item.id}.png", item.status, len(item.issues)])
    return path


def read_report(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _strip_ms(report: dict) -> dict:
    copy = json.loads(json.dumps(report, ensure_ascii=False))
    for item in copy.get("items", []):
        item.pop("ms", None)
    return copy


def diff_reports(run1: dict, run2: dict) -> dict:
    """逐字段对比两次报告；ms 是耗时，不参与 diff。"""
    rows: list[dict] = []
    for field in ("total", "ok", "violations"):
        if run1.get(field) != run2.get(field):
            rows.append({"scope": "batch", "id": "-", "field": field, "run1": run1.get(field), "run2": run2.get(field)})

    items1 = {item["id"]: item for item in run1.get("items", [])}
    items2 = {item["id"]: item for item in run2.get("items", [])}
    for item_id in sorted(set(items1) | set(items2)):
        left = items1.get(item_id)
        right = items2.get(item_id)
        if left is None or right is None:
            rows.append(
                {
                    "scope": "item",
                    "id": item_id,
                    "field": "存在性",
                    "run1": "有" if left else "无",
                    "run2": "有" if right else "无",
                }
            )
            continue
        if left.get("status") != right.get("status"):
            rows.append({"scope": "item", "id": item_id, "field": "status", "run1": left.get("status"), "run2": right.get("status")})
        for name in sorted(set(left.get("chars", {})) | set(right.get("chars", {}))):
            if left.get("chars", {}).get(name) != right.get("chars", {}).get(name):
                rows.append(
                    {
                        "scope": "item",
                        "id": item_id,
                        "field": f"chars.{name}",
                        "run1": left.get("chars", {}).get(name),
                        "run2": right.get("chars", {}).get(name),
                    }
                )
        for name in sorted(set(left.get("image", {})) | set(right.get("image", {}))):
            if left.get("image", {}).get(name) != right.get("image", {}).get(name):
                rows.append(
                    {
                        "scope": "item",
                        "id": item_id,
                        "field": f"image.{name}",
                        "run1": left.get("image", {}).get(name),
                        "run2": right.get("image", {}).get(name),
                    }
                )
        codes1 = sorted({issue["code"] for issue in left.get("issues", [])})
        codes2 = sorted({issue["code"] for issue in right.get("issues", [])})
        if codes1 != codes2:
            rows.append(
                {
                    "scope": "item",
                    "id": item_id,
                    "field": "issues",
                    "run1": ",".join(codes1) or "-",
                    "run2": ",".join(codes2) or "-",
                }
            )

    counters = issue_counts(run1)
    counters2 = issue_counts(run2)
    issue_codes = {
        code: {"run1": counters.get(code, 0), "run2": counters2.get(code, 0)}
        for code in sorted(set(counters) | set(counters2))
    }
    return {"changed": bool(rows), "rows": rows, "issue_codes": issue_codes}


def issue_counts(report: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in report.get("items", []):
        for issue in item.get("issues", []):
            counts[issue["code"]] = counts.get(issue["code"], 0) + 1
    return counts


def diff_markdown(diff: dict) -> str:
    lines = ["| 范围 | id | 字段 | 第一遍 | 第二遍 |", "|---|---|---|---|---|"]
    if not diff["rows"]:
        lines.append("| - | - | 无差异 | - | - |")
    for row in diff["rows"]:
        lines.append(f"| {row['scope']} | {row['id']} | {row['field']} | {row['run1']} | {row['run2']} |")
    lines.append("")
    lines.append("| issue code | 第一遍 | 第二遍 |")
    lines.append("|---|---|---|")
    for code, counter in diff["issue_codes"].items():
        lines.append(f"| `{code}` | {counter['run1']} | {counter['run2']} |")
    return "\n".join(lines) + "\n"
