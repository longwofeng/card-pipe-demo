"""demo 子命令：改一条规则重跑 → diff 含 title_too_long → PASS。"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    environment.pop("CARDPIPE_FONT", None)
    return subprocess.run(
        [sys.executable, "-m", "app.cli", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        timeout=300,
    )


def test_demo_returns_pass_and_diff(tmp_path):
    rules_path = ROOT / "rules.yaml"
    before = hashlib.sha256(rules_path.read_bytes()).hexdigest()
    out = tmp_path / "acceptance"

    proc = run_cli("demo", "--out", str(out))

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "PASS" in proc.stdout
    assert "title_chars=12" in proc.stdout

    diff = json.loads((out / "report_diff.json").read_text(encoding="utf-8"))
    assert diff["issue_codes"]["title_too_long"]["run1"] == 0
    assert diff["issue_codes"]["title_too_long"]["run2"] >= 1
    assert diff["changed"] is True

    markdown = (out / "report_diff.md").read_text(encoding="utf-8")
    assert "title_too_long" in markdown

    for run in ("run1", "run2"):
        assert (out / run / "batch.pdf").is_file()
        assert len(list((out / run).glob("item_*.png"))) == 6
        assert (out / run / "report.json").is_file()

    after = hashlib.sha256(rules_path.read_bytes()).hexdigest()
    assert after == before, "demo 不应改动仓库里的 rules.yaml"
