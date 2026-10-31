"""CLI 契约：产物、退出码、provider 与自检。"""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment.pop("CARDPIPE_FONT", None)
    if env:
        environment.update(env)
    return subprocess.run(
        [sys.executable, "-m", "app.cli", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        timeout=180,
    )


def build_args(out: Path, *extra: str) -> list[str]:
    return [
        "build",
        "--items",
        "data/items.yaml",
        "--template",
        "templates/card_a.json",
        "--rules",
        "rules.yaml",
        "--out",
        str(out),
        *extra,
    ]


def test_build_local_creates_all_artifacts(tmp_path):
    out = tmp_path / "demo1"
    proc = run_cli(*build_args(out))
    assert proc.returncode == 0, proc.stderr
    assert (out / "item_001.png").is_file()
    assert (out / "batch.pdf").is_file()
    assert (out / "report.json").is_file()
    assert (out / "manifest.csv").is_file()

    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["total"] == 6
    assert len(report["items"]) == 6
    assert "处理条数: 6" in proc.stdout
    assert "输出目录" in proc.stdout

    with (out / "manifest.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["id", "output", "status", "issues"]
    assert len(rows) == 7


def test_pdf_pages_match_canvas(tmp_path):
    out = tmp_path / "pdf"
    proc = run_cli(*build_args(out))
    assert proc.returncode == 0, proc.stderr
    raw = (out / "batch.pdf").read_bytes()
    boxes = re.findall(rb"/MediaBox\s*\[\s*0\s+0\s+([0-9.]+)\s+([0-9.]+)\s*\]", raw)
    assert boxes, "PDF 中没有 MediaBox"
    # 1080x1440 @144dpi -> 540x720 pt
    assert {tuple(round(float(value), 1) for value in box) for box in boxes} == {(540.0, 720.0)}
    pages = re.findall(rb"/Type\s*/Page[^s]", raw)
    assert len(pages) == 6


def test_mock_provider_runs(tmp_path):
    out = tmp_path / "mock"
    proc = run_cli(*build_args(out, "--provider", "mock"))
    assert proc.returncode == 0, proc.stderr
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert all(entry["image"] == {"w": 800, "h": 800} for entry in report["items"])
    assert (out / "item_001.png").is_file()


def test_missing_font_exits_3(tmp_path):
    proc = run_cli(*build_args(tmp_path / "nofont"), env={"CARDPIPE_FONT": str(tmp_path / "missing.ttf")})
    assert proc.returncode == 3
    assert "字体缺失" in proc.stderr


def test_bad_items_exits_4(tmp_path):
    bad = tmp_path / "items.yaml"
    bad.write_text("items:\n  - title: 没有 id\n", encoding="utf-8")
    proc = run_cli(
        "build",
        "--items",
        str(bad),
        "--template",
        "templates/card_a.json",
        "--rules",
        "rules.yaml",
        "--out",
        str(tmp_path / "bad"),
    )
    assert proc.returncode == 4
    assert "[INPUT]" in proc.stderr


def test_fail_mode_exits_2_without_products(tmp_path):
    rules = tmp_path / "rules_fail.yaml"
    rules.write_text(
        (ROOT / "rules.yaml").read_text(encoding="utf-8").replace("on_violation: report", "on_violation: fail"),
        encoding="utf-8",
    )
    out = tmp_path / "fail"
    proc = run_cli(
        "build",
        "--items",
        "data/items.yaml",
        "--template",
        "templates/card_a.json",
        "--rules",
        str(rules),
        "--out",
        str(out),
    )
    assert proc.returncode == 2
    assert list(out.glob("*.png")) == []
    assert list(out.glob("*.pdf")) == []
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    # 违规条目标记 failed；其余条目本身通过校验，但整批未产出
    assert any(entry["status"] == "failed" for entry in report["items"])
    assert report["violations"] >= 1
    assert len(report["items"]) == 6


def test_selfcheck_reports_all_ok():
    proc = run_cli("selfcheck")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "[FAIL]" not in proc.stdout
    assert "自检通过" in proc.stdout

