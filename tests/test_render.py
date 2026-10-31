"""排版与合成：画布尺寸、中文字形、换行裁剪、图片适配。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.cli import load_items
from app.materials import LocalProvider
from app.models import Canvas, Item, Template, TextSlot
from app.render import Renderer, fit_image, load_font, load_template, resolve_font_path, round_corners, wrap_text

ROOT = Path(__file__).resolve().parents[1]
FONT_PATH = resolve_font_path()


def ink_pixels(image: Image.Image, background=(255, 255, 255)) -> int:
    raw = image.convert("RGB").tobytes()
    background_bytes = bytes(background)
    return sum(1 for index in range(0, len(raw), 3) if raw[index : index + 3] != background_bytes)


def title_template() -> Template:
    return Template(
        canvas=Canvas(width=600, height=200, background="#FFFFFF"),
        slots=[
            TextSlot(
                name="title",
                x=20,
                y=20,
                w=560,
                h=160,
                font_size=48,
                line_height=1.2,
                color="#111111",
                max_lines=2,
                align="left",
            )
        ],
    )


def test_rendered_image_matches_canvas():
    template = load_template(ROOT / "templates" / "card_a.json")
    renderer = Renderer(template, FONT_PATH)
    item = load_items(ROOT / "data" / "items.yaml")[0]
    provider = LocalProvider(ROOT, 800, 800, 920 / 720)
    image, _ = provider.resolve(item)
    result = renderer.render(item, image)
    assert result.image.size == (template.canvas.width, template.canvas.height)


def test_chinese_title_is_not_blank():
    renderer = Renderer(title_template(), FONT_PATH)
    result = renderer.render(Item(id="ink", title="低空政务巡查"), Image.new("RGB", (8, 8), "white"))
    slot_area = result.image.crop((20, 20, 580, 180))
    ratio = ink_pixels(slot_area) / (slot_area.width * slot_area.height)
    assert ratio > 0.05, f"标题槽位非背景像素比例过低：{ratio:.2%}"


def test_text_is_clipped_inside_slot():
    template = Template(
        canvas=Canvas(width=600, height=300, background="#FFFFFF"),
        slots=[
            TextSlot(
                name="title",
                x=20,
                y=20,
                w=560,
                h=80,
                font_size=48,
                line_height=1.2,
                color="#111111",
                max_lines=2,
                align="left",
            )
        ],
    )
    renderer = Renderer(template, FONT_PATH)
    item = Item(id="clip", title="低空政务巡查智能体" * 6)
    result = renderer.render(item, Image.new("RGB", (8, 8), "white"))
    assert ink_pixels(result.image.crop((0, 100, 600, 300))) == 0
    assert ink_pixels(result.image.crop((20, 20, 580, 100))) > 0
    assert result.layouts["title"].overflow_lines > 0


def test_chinese_wrap_by_character_width():
    font = load_font(FONT_PATH, 32)
    lines = wrap_text("春季新品上市春季新品上市春季新品上市", font, 200)
    assert len(lines) > 1
    assert all(font.getlength(line) <= 200 for line in lines)


def test_english_wrap_keeps_words():
    font = load_font(FONT_PATH, 32)
    text = "low altitude patrol drone spring edition"
    lines = wrap_text(text, font, 180)
    assert len(lines) > 1
    assert " ".join(line.strip() for line in lines).split() == text.split()
    assert all(font.getlength(line) <= 180 for line in lines)


def test_cover_and_contain_fit_slot():
    source = Image.new("RGB", (400, 200), (10, 120, 200))
    cover = fit_image(source, 300, 300, "cover")
    contain = fit_image(source, 300, 300, "contain")
    assert cover.size == (300, 300)
    assert contain.size == (300, 300)
    assert contain.getpixel((0, 0))[3] == 0
    assert contain.getpixel((150, 150))[3] == 255
    assert cover.getpixel((0, 0))[3] == 255


def test_round_corners_mask():
    layer = Image.new("RGBA", (200, 200), (255, 0, 0, 255))
    rounded = round_corners(layer, 24)
    assert rounded.getpixel((0, 0))[3] == 0
    assert rounded.getpixel((100, 100))[3] == 255
