"""生成 assets/images 下的测试素材：纯本地绘制，确定性、无网络。

运行：python scripts/make_assets.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT_DIR = Path(__file__).resolve().parents[1] / "assets" / "images"

SPECS = [
    ("hero_01.png", (1150, 900), ((238, 242, 238), (44, 88, 72)), (246, 250, 246), 1),
    ("hero_02.png", (1150, 900), ((240, 246, 252), (22, 58, 96)), (255, 214, 140), 2),
    ("hero_03.png", (1150, 900), ((232, 238, 240), (18, 42, 58)), (120, 200, 190), 3),
    ("wide.png", (1600, 900), ((250, 238, 220), (120, 70, 40)), (255, 250, 240), 4),
    ("small.png", (600, 600), ((240, 232, 246), (70, 40, 90)), (240, 220, 255), 5),
]


def gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size, top)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / max(height - 1, 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))
        draw.line([(0, y), (width, y)], fill=color)
    return image


def soft_ellipse(size: tuple[int, int], box: tuple[int, int, int, int], color: tuple[int, ...], blur: int) -> Image.Image:
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse(box, fill=color)
    return layer.filter(ImageFilter.GaussianBlur(blur))


def make(name: str, size: tuple[int, int], palette, accent, variant: int) -> Path:
    width, height = size
    base = gradient(size, palette[0], palette[1])

    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    glow.alpha_composite(
        soft_ellipse(size, (-width // 3, -height // 2, int(width * 0.75), int(height * 0.85)), (*accent, 95), max(8, min(size) // 14))
    )
    glow.alpha_composite(
        soft_ellipse(size, (int(width * 0.45), int(height * 0.3), int(width * 1.3), int(height * 1.35)), (*palette[0], 80), max(8, min(size) // 10))
    )
    image = Image.alpha_composite(base.convert("RGBA"), glow)

    body_layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(body_layer)
    center_x = int(width * (0.40 + variant * 0.03))
    center_y = int(height * 0.52)
    body_w = int(width * 0.34)
    body_h = int(height * 0.46)
    radius = int(min(body_w, body_h) * 0.24)
    draw.rounded_rectangle(
        [center_x - body_w // 2, center_y - body_h // 2, center_x + body_w // 2, center_y + body_h // 2],
        radius=radius,
        fill=(*accent, 240),
    )
    draw.rounded_rectangle(
        [center_x - body_w // 2 + 20, center_y - body_h // 2 + 20, center_x - body_w // 2 + 20 + body_w // 6, center_y + body_h // 2 - 20],
        radius=radius // 2,
        fill=(255, 255, 255, 80),
    )
    body_layer = body_layer.rotate(14 - variant * 2, resample=Image.Resampling.BICUBIC, center=(center_x, center_y))
    image = Image.alpha_composite(image, body_layer)

    grid = Image.new("RGBA", size, (0, 0, 0, 0))
    grid_draw = ImageDraw.Draw(grid)
    step = max(48, min(size) // 14)
    for x in range(0, width, step):
        grid_draw.line([(x, 0), (x, height)], fill=(255, 255, 255, 16))
    for y in range(0, height, step):
        grid_draw.line([(0, y), (width, y)], fill=(255, 255, 255, 16))
    image = Image.alpha_composite(image, grid).convert("RGB")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / name
    image.save(path, format="PNG", optimize=True)
    return path


def main() -> None:
    for name, size, palette, accent, variant in SPECS:
        path = make(name, size, palette, accent, variant)
        print(f"{path.name}: {size[0]}x{size[1]}")


if __name__ == "__main__":
    main()
