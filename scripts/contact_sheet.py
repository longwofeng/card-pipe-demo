"""把一批成品 PNG 拼成一张联系表，便于转发与审阅。

用法：
    python scripts/contact_sheet.py out/people --out out/people/contact_sheet.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.render import load_font, resolve_font_path  # noqa: E402


def build_sheet(files: list[Path], output: Path, columns: int, thumb_width: int) -> Path:
    gap = 28
    margin = 40
    caption_height = 34
    font_path = resolve_font_path()
    font = load_font(font_path, 22)

    thumbs = []
    for path in files:
        with Image.open(path) as raw:
            image = raw.convert("RGB")
        height = round(image.height * thumb_width / image.width)
        thumbs.append((path.stem, image.resize((thumb_width, height), Image.Resampling.LANCZOS)))

    rows = (len(thumbs) + columns - 1) // columns
    cell_height = max(image.height for _, image in thumbs) + caption_height
    width = margin * 2 + columns * thumb_width + (columns - 1) * gap
    height = margin * 2 + rows * cell_height + (rows - 1) * gap

    sheet = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    for index, (label, image) in enumerate(thumbs):
        row, column = divmod(index, columns)
        left = margin + column * (thumb_width + gap)
        top = margin + row * (cell_height + gap)
        sheet.paste(image, (left, top))
        draw.rectangle([left, top, left + thumb_width - 1, top + image.height - 1], outline=(226, 226, 226))
        draw.text((left, top + image.height + 8), label, font=font, fill=(110, 110, 110))

    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, format="PNG", optimize=True)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="成品图联系表")
    parser.add_argument("directory", help="包含 PNG 的目录")
    parser.add_argument("--out", default=None, help="输出文件，默认 <directory>/contact_sheet.png")
    parser.add_argument("--columns", type=int, default=3)
    parser.add_argument("--width", type=int, default=360, help="单张缩略图宽度")
    args = parser.parse_args()

    directory = Path(args.directory)
    output = Path(args.out) if args.out else directory / "contact_sheet.png"
    files = sorted(
        path for path in directory.glob("*.png")
        if path.resolve() != output.resolve()
    )
    if not files:
        raise SystemExit(f"{directory} 下没有 PNG")
    result = build_sheet(files, output, max(1, args.columns), max(120, args.width))
    print(f"{result}: {len(files)} 张，{result.stat().st_size} bytes")


if __name__ == "__main__":
    main()
