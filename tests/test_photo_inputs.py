"""真实照片的机械差异：EXIF 方向、大尺寸 JPEG、横图比例。

用合成 JPEG 覆盖，不依赖任何真人照片或图库授权。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from app.cli import build_batch
from app.materials import LocalProvider, load_image_file
from app.models import Item
from app.render import load_template
from app.rules import load_rules, validate_item

ROOT = Path(__file__).resolve().parents[1]
PERSON_TEMPLATE = load_template(ROOT / "templates" / "card_person.json")
RULE = load_rules(ROOT / "rules.yaml")


def make_phone_jpeg(path: Path, size: tuple[int, int], orientation: int | None = None) -> Path:
    image = Image.new("RGB", size, (255, 255, 255))
    ImageDraw.Draw(image).rectangle([0, 0, 300, 300], fill=(220, 30, 30))
    exif = Image.Exif()
    if orientation is not None:
        exif[274] = orientation  # 274 = Orientation
    image.save(path, "JPEG", quality=92, exif=exif)
    return path


def test_exif_orientation_is_applied_on_load(tmp_path):
    stored = make_phone_jpeg(tmp_path / "rotated.jpg", (1200, 800), orientation=6)
    loaded = load_image_file(stored)
    # Orientation=6 表示“顺时针旋转 90° 才是正确方向”
    assert loaded.size == (800, 1200)
    red = loaded.getpixel((750, 60))
    assert red[0] > 150 and red[1] < 90
    white = loaded.getpixel((60, 60))
    assert min(white) > 240


def test_provider_reports_displayed_dimensions(tmp_path):
    stored = make_phone_jpeg(tmp_path / "rotated.jpg", (1200, 800), orientation=6)
    provider = LocalProvider(tmp_path)
    image, meta = provider.resolve(Item(id="exif", image=str(stored)))
    assert image.size == (800, 1200)
    assert meta == {"w": 800, "h": 1200, "source": "local"}


def test_large_phone_jpeg_renders_to_canvas(tmp_path):
    photo = make_phone_jpeg(tmp_path / "phone.jpg", (3024, 4032))
    item = Item(
        id="phone_001",
        title="林晚晴",
        subtitle="社区巡检负责人",
        body="负责 3 个街道的日常巡查排班与工单闭环。",
        bullets=["工单闭环", "街道协同"],
        image=str(photo),
    )
    outcome = build_batch([item], PERSON_TEMPLATE, RULE, tmp_path / "out")
    assert outcome.produced is True
    assert outcome.report.items[0].issues == []
    png = Image.open(outcome.out_dir / "phone_001.png")
    assert png.size == (PERSON_TEMPLATE.canvas.width, PERSON_TEMPLATE.canvas.height)


def test_landscape_phone_photo_flagged_by_portrait_slot(tmp_path):
    photo = make_phone_jpeg(tmp_path / "landscape.jpg", (4032, 3024))
    item = Item(id="phone_002", title="合影", subtitle="团队合影", body="横版手机照片。", image=str(photo))
    codes = [issue.code for issue in validate_item(item, RULE, PERSON_TEMPLATE, {"w": 4032, "h": 3024})]
    assert "image_ratio_off" in codes
    assert "image_too_small" not in codes

