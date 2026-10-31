"""规则边界与三态处理。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cli import build_batch
from app.models import Item, Rule
from app.render import load_template
from app.rules import load_rules, truncate_text, validate_item

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = load_template(ROOT / "templates" / "card_a.json")
RULE = load_rules(ROOT / "rules.yaml")
GOOD_IMAGE = {"w": 1150, "h": 900, "source": "local"}


def codes(issues) -> list[str]:
    return [issue.code for issue in issues]


def make_item(**overrides) -> Item:
    data = {
        "id": "probe",
        "title": "春季新品上市",
        "subtitle": "轻量 · 透气 · 三色可选",
        "body": "这是一段正文，描述产品的核心卖点与适用场景。",
        "bullets": ["三层透气网布", "单只 180g"],
        "image": "assets/images/hero_01.png",
    }
    data.update(overrides)
    return Item.model_validate(data)


def test_title_chars_boundary():
    assert "title_too_long" not in codes(validate_item(make_item(title="春" * 18), RULE, TEMPLATE, GOOD_IMAGE))
    assert "title_too_long" in codes(validate_item(make_item(title="春" * 19), RULE, TEMPLATE, GOOD_IMAGE))


def test_subtitle_and_body_boundary():
    assert "subtitle_too_long" not in codes(validate_item(make_item(subtitle="副" * 24), RULE, TEMPLATE, GOOD_IMAGE))
    assert "subtitle_too_long" in codes(validate_item(make_item(subtitle="副" * 25), RULE, TEMPLATE, GOOD_IMAGE))
    assert "body_too_long" not in codes(validate_item(make_item(body="正" * 120), RULE, TEMPLATE, GOOD_IMAGE))
    assert "body_too_long" in codes(validate_item(make_item(body="正" * 121), RULE, TEMPLATE, GOOD_IMAGE))


def test_bullets_max_boundary():
    four = make_item(bullets=["甲乙", "丙丁", "戊己", "庚辛"])
    five = make_item(bullets=["甲乙", "丙丁", "戊己", "庚辛", "壬癸"])
    assert "too_many_bullets" not in codes(validate_item(four, RULE, TEMPLATE, GOOD_IMAGE))
    assert "too_many_bullets" in codes(validate_item(five, RULE, TEMPLATE, GOOD_IMAGE))


def test_image_min_size_boundary():
    assert "image_too_small" not in codes(validate_item(make_item(), RULE, TEMPLATE, {"w": 800, "h": 800}))
    assert "image_too_small" in codes(validate_item(make_item(), RULE, TEMPLATE, {"w": 799, "h": 800}))
    assert "image_too_small" in codes(validate_item(make_item(), RULE, TEMPLATE, {"w": 800, "h": 799}))


def square_template() -> dict:
    return {
        "canvas": {"width": 1000, "height": 1000, "background": "#FFFFFF"},
        "slots": [
            {"type": "text", "name": "title", "x": 0, "y": 0, "w": 900, "h": 100, "font_size": 40, "max_lines": 2},
            {"type": "image", "name": "hero", "x": 0, "y": 200, "w": 1000, "h": 1000, "fit": "cover"},
        ],
    }


def square_rule(tolerance: float = 0.25, on_violation: str = "report") -> Rule:
    return Rule.model_validate(
        {
            "limits": {"title_chars": 18, "subtitle_chars": 24, "body_chars": 120, "bullets_max": 4},
            "image": {"min_width": 100, "min_height": 100, "ratio_tolerance": tolerance},
            "on_violation": on_violation,
            "output": {"png_dpi": 72, "pdf": True},
        }
    )


def test_ratio_tolerance_boundary(tmp_path):
    template = load_template(write_json(tmp_path / "square.json", square_template()))
    rule = square_rule(0.25)
    # 槽位比例 1.0；图片 1000x800 = 1.25，与容差 0.25 恰好相等：不报
    assert "image_ratio_off" not in codes(validate_item(make_item(), rule, template, {"w": 1000, "h": 800}))
    # 图片 1000x790 = 1.2658，超容差：报
    assert "image_ratio_off" in codes(validate_item(make_item(), rule, template, {"w": 1000, "h": 790}))
    # 图片 800x1000 = 0.8，差 0.2 < 0.25：不报
    assert "image_ratio_off" not in codes(validate_item(make_item(), rule, template, {"w": 800, "h": 1000}))


def write_json(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_missing_field():
    issues = validate_item(make_item(subtitle=""), RULE, TEMPLATE, GOOD_IMAGE)
    assert "missing_field" in codes(issues)
    assert [issue.field for issue in issues if issue.code == "missing_field"] == ["subtitle"]


def test_truncate_text_keeps_limit():
    assert truncate_text("一二三四五六", 6) == "一二三四五六"
    truncated = truncate_text("一二三四五六七", 6)
    assert len(truncated) == 6
    assert truncated.endswith("…")


def build_with(tmp_path: Path, rule: Rule, item: Item):
    template = load_template(ROOT / "templates" / "card_a.json")
    parent = tmp_path / f"batch_{rule.on_violation}"
    return build_batch([item], template, rule, parent, provider="local")


def test_on_violation_report(tmp_path):
    rule = RULE.model_copy(update={"on_violation": "report"})
    outcome = build_with(tmp_path, rule, make_item(title="春" * 19))
    assert outcome.produced is True
    assert outcome.report.items[0].status == "ok_with_issues"
    assert "title_too_long" in codes(outcome.report.items[0].issues)
    assert (outcome.out_dir / "probe.png").is_file()
    assert (outcome.out_dir / "batch.pdf").is_file()


def test_on_violation_truncate(tmp_path):
    rule = RULE.model_copy(update={"on_violation": "truncate"})
    outcome = build_with(tmp_path, rule, make_item(title="春" * 19))
    assert outcome.produced is True
    report_item = outcome.report.items[0]
    assert report_item.status == "truncated"
    assert report_item.chars["title"] == RULE.limits.title_chars
    assert "truncated" in codes(report_item.issues)
    assert report_item.issues[-1].field == "title"
    assert (outcome.out_dir / "probe.png").is_file()


def test_on_violation_fail(tmp_path):
    rule = RULE.model_copy(update={"on_violation": "fail"})
    outcome = build_with(tmp_path, rule, make_item(title="春" * 19))
    assert outcome.produced is False
    assert outcome.report.items[0].status == "failed"
    assert "title_too_long" in codes(outcome.report.items[0].issues)
    assert list(outcome.out_dir.glob("*.png")) == []
    assert list(outcome.out_dir.glob("*.pdf")) == []
    assert (outcome.out_dir / "report.json").is_file()
