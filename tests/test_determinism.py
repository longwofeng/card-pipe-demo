"""确定性：同输入 + 同规则 → 报告除 ms 外逐字段一致。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_build(out: Path) -> subprocess.CompletedProcess:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment.pop("CARDPIPE_FONT", None)
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "app.cli",
            "build",
            "--items",
            "data/items.yaml",
            "--template",
            "templates/card_a.json",
            "--rules",
            "rules.yaml",
            "--out",
            str(out),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        timeout=180,
    )


def strip_ms(report: dict) -> dict:
    copy = json.loads(json.dumps(report, ensure_ascii=False))
    for item in copy.get("items", []):
        item.pop("ms", None)
    return copy


def test_report_is_deterministic(tmp_path):
    # 两次输出目录同名（batch 取目录名），只比较内容
    first = tmp_path / "run_a" / "demo"
    second = tmp_path / "run_b" / "demo"
    assert run_build(first).returncode == 0
    assert run_build(second).returncode == 0

    report_a = json.loads((first / "report.json").read_text(encoding="utf-8"))
    report_b = json.loads((second / "report.json").read_text(encoding="utf-8"))
    assert strip_ms(report_a) == strip_ms(report_b)

    # issue 的顺序也固定（先字数、再缺字段、最后图片），不只是集合一致
    order_a = [[issue["code"] for issue in entry["issues"]] for entry in report_a["items"]]
    order_b = [[issue["code"] for issue in entry["issues"]] for entry in report_b["items"]]
    assert order_a == order_b
    assert any(order_a), "样例批次应至少含一个 issue，否则确定性测试没有意义"

