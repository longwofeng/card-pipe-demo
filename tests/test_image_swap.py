"""图像侧：人物素材替换、人像校验与授权登记。"""

from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

from app import cli
from app.cli import build_batch, load_items
from app.models import Rule
from app.render import Renderer, load_template, resolve_font_path
from app.rules import load_rules, validate_item

ROOT = Path(__file__).resolve().parents[1]
PEOPLE = ROOT / "data" / "items_people.yaml"
PERSON_TEMPLATE = ROOT / "templates" / "card_person.json"
PRODUCT_TEMPLATE = ROOT / "templates" / "card_a.json"
RULE = load_rules(ROOT / "rules.yaml")


def test_person_template_renders_portrait_slot():
    template = load_template(PERSON_TEMPLATE)
    renderer = Renderer(template, resolve_font_path())
    item = load_items(PEOPLE)[0]
    image = Image.open(ROOT / "assets" / "images" / "people" / "p01.png").convert("RGB")
    result = renderer.render(item, image)
    assert result.image.size == (template.canvas.width, template.canvas.height)
    # 人像槽位区域应当有实际像素（不是空白）
    portrait = result.image.crop((72, 120, 632, 860))
    raw = portrait.tobytes()
    colors = {raw[index : index + 3] for index in range(0, len(raw), 3)}
    assert len(colors) > 20


def test_people_batch_flags_small_and_mismatched_images(tmp_path):
    items = load_items(PEOPLE)
    template = load_template(PERSON_TEMPLATE)
    outcome = build_batch(items, template, RULE, tmp_path / "people")
    assert outcome.produced is True
    report = {entry.id: entry for entry in outcome.report.items}

    assert report["person_001"].status == "ok"
    assert report["person_002"].status == "ok"
    assert report["person_003"].status == "ok"
    assert [issue.code for issue in report["person_004"].issues] == ["image_too_small"]
    assert [issue.code for issue in report["person_005"].issues] == ["image_ratio_off"]
    assert outcome.report.total == 5
    assert outcome.report.violations == 2

    for item in items:
        assert (outcome.out_dir / f"{item.id}.png").is_file()
    assert (outcome.out_dir / "batch.pdf").is_file()


def test_same_portrait_flagged_in_landscape_product_template():
    item = load_items(PEOPLE)[0]
    meta = {"w": 900, "h": 1200, "source": "local"}
    person_codes = [issue.code for issue in validate_item(item, RULE, load_template(PERSON_TEMPLATE), meta)]
    product_codes = [issue.code for issue in validate_item(item, RULE, load_template(PRODUCT_TEMPLATE), meta)]
    assert "image_ratio_off" not in person_codes
    assert "image_ratio_off" in product_codes


def test_every_person_asset_is_registered():
    people_dir = ROOT / "assets" / "images" / "people"
    manifest = (people_dir / "SOURCES.md").read_text(encoding="utf-8")
    files = sorted(path.name for path in people_dir.iterdir() if path.suffix.lower() == ".png")
    assert files, "人物素材目录不应为空"
    for name in files:
        assert name in manifest, f"{name} 未在 SOURCES.md 登记"
    ok, label, detail = cli._asset_provenance()
    assert ok, f"{label}: {detail}"


def test_provenance_check_rejects_unregistered_file(tmp_path, monkeypatch):
    people_dir = tmp_path / "assets" / "images" / "people"
    people_dir.mkdir(parents=True)
    shutil.copy(ROOT / "assets" / "images" / "people" / "p01.png", people_dir / "new_hire.png")
    (people_dir / "SOURCES.md").write_text("# 登记表\n", encoding="utf-8")

    monkeypatch.setattr(cli, "ROOT", tmp_path)
    ok, _, detail = cli._asset_provenance()
    assert ok is False
    assert "new_hire.png" in detail

    (people_dir / "SOURCES.md").write_text("# 登记表\nnew_hire.png 自制\n", encoding="utf-8")
    ok, _, _ = cli._asset_provenance()
    assert ok is True

