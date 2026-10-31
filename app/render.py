"""模板解析、文本排版、图片合成、PNG/PDF 导出。

本模块不读写 YAML、不做规则判定；输入是已经解析好的 Template / Rule / Item。
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .models import ImageSlot, Item, Template, TextSlot

DEFAULT_FONT = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "NotoSansSC-Regular.ttf"


class FontMissing(RuntimeError):
    """字体缺失：必须显式失败，绝不静默画方块。"""


class TemplateError(ValueError):
    """模板 JSON 缺失或格式错误。"""


@dataclass
class TextLayout:
    name: str
    total_lines: int
    max_lines: int
    dropped_lines: int = 0
    overflow_lines: int = 0


@dataclass
class RenderResult:
    image: Image.Image
    layouts: dict[str, TextLayout] = field(default_factory=dict)


def resolve_font_path(explicit: str | Path | None = None) -> Path:
    """字体路径：显式参数 > CARDPIPE_FONT 环境变量 > 仓库自带字体。"""
    if explicit:
        return Path(explicit).expanduser()
    from_env = os.environ.get("CARDPIPE_FONT")
    if from_env:
        return Path(from_env).expanduser()
    return DEFAULT_FONT


def load_font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    path = Path(path)
    if not path.is_file():
        raise FontMissing(
            f"中文字体缺失：{path}\n"
            "请把 NotoSansSC-Regular.ttf 放到 assets/fonts/ 下（或用 CARDPIPE_FONT 指定路径）。"
            "没有中文字体时会画出方块，因此这里直接退出。"
        )
    try:
        return ImageFont.truetype(str(path), size)
    except OSError as exc:
        raise FontMissing(f"字体无法加载：{path}（{exc}）") from exc


def load_template(path: Path) -> Template:
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TemplateError(f"读取模板失败 {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise TemplateError(f"模板不是合法 JSON {path}: {exc}") from exc
    from pydantic import ValidationError

    try:
        return Template.model_validate(raw)
    except ValidationError as exc:
        raise TemplateError(f"模板字段错误 {path}:\n{exc}") from exc


_CJK_RANGES = (
    (0x1100, 0x11FF),
    (0x2E80, 0x303F),
    (0x3040, 0x30FF),
    (0x3400, 0x4DBF),
    (0x4E00, 0x9FFF),
    (0xAC00, 0xD7AF),
    (0xF900, 0xFAFF),
    (0xFF00, 0xFFEF),
)


def is_cjk(char: str) -> bool:
    code = ord(char)
    return any(start <= code <= end for start, end in _CJK_RANGES)


def _tokens(paragraph: str) -> list[str]:
    """中文按字切分，英文按空格断词。"""
    tokens: list[str] = []
    buffer = ""
    for char in paragraph:
        if char.isspace():
            if buffer:
                tokens.append(buffer)
                buffer = ""
            tokens.append(" ")
        elif is_cjk(char):
            if buffer:
                tokens.append(buffer)
                buffer = ""
            tokens.append(char)
        else:
            buffer += char
    if buffer:
        tokens.append(buffer)
    return tokens


def _hard_break(text: str, font: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        if current and font.getlength(current + char) > max_width:
            lines.append(current)
            current = char
        else:
            current += char
    if current:
        lines.append(current)
    return lines


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    """先测量后换行：返回按槽位宽度折好的行。"""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        tokens = _tokens(paragraph)
        if not tokens:
            lines.append("")
            continue
        current = ""
        for token in tokens:
            if not current and token == " ":
                continue
            candidate = current + token
            if current and font.getlength(candidate.rstrip()) > max_width:
                lines.append(current.rstrip())
                current = "" if token == " " else token
            else:
                current = candidate
        if current:
            if font.getlength(current) > max_width:
                lines.extend(_hard_break(current, font, max_width))
            else:
                lines.append(current.rstrip())
        else:
            lines.append("")
    while lines and lines[-1] == "":
        lines.pop()
    return lines or [""]


def fit_lines(lines: list[str], font: ImageFont.FreeTypeFont, max_width: float, max_lines: int) -> tuple[list[str], int]:
    """截断到 max_lines 行，末行加省略号（truncate 模式）。"""
    if len(lines) <= max_lines:
        return lines, 0
    kept = list(lines[:max_lines])
    last = kept[-1]
    while last and font.getlength(last + "…") > max_width:
        last = last[:-1]
    kept[-1] = (last.rstrip() + "…") if last else "…"
    return kept, len(lines) - max_lines


def slot_text(item: Item, slot: TextSlot) -> str:
    if slot.name == "bullets":
        prefix = slot.prefix or ""
        return "\n".join(f"{prefix}{bullet}" for bullet in item.bullets if bullet)
    value = getattr(item, slot.name, "") or ""
    if slot.prefix:
        return "\n".join(f"{slot.prefix}{line}" for line in value.split("\n"))
    return value


def fit_image(image: Image.Image, width: int, height: int, mode: str) -> Image.Image:
    """cover：按短边缩放后居中裁剪；contain：等比缩放后居中留白。"""
    source = image.convert("RGB")
    if mode == "cover":
        scale = max(width / source.width, height / source.height)
        resized_size = (max(1, math.ceil(source.width * scale)), max(1, math.ceil(source.height * scale)))
        resized = source.resize(resized_size, Image.Resampling.LANCZOS)
        left = (resized_size[0] - width) // 2
        top = (resized_size[1] - height) // 2
        return resized.crop((left, top, left + width, top + height)).convert("RGBA")
    scale = min(width / source.width, height / source.height)
    resized_size = (max(1, round(source.width * scale)), max(1, round(source.height * scale)))
    resized = source.resize(resized_size, Image.Resampling.LANCZOS).convert("RGBA")
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    layer.paste(resized, ((width - resized_size[0]) // 2, (height - resized_size[1]) // 2))
    return layer


def round_corners(image: Image.Image, radius: int) -> Image.Image:
    if radius <= 0:
        return image
    limit = min(image.width, image.height) // 2
    radius = min(radius, limit)
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, image.width - 1, image.height - 1], radius=radius, fill=255
    )
    result = image.convert("RGBA")
    result.putalpha(mask)
    return result


def _draw_text_slot(
    canvas: Image.Image,
    slot: TextSlot,
    text: str,
    font: ImageFont.FreeTypeFont,
    truncate: bool,
) -> TextLayout:
    lines = wrap_text(text, font, slot.w)
    total = len(lines)
    dropped = 0
    overflow = 0
    if total > slot.max_lines:
        if truncate:
            lines, dropped = fit_lines(lines, font, slot.w, slot.max_lines)
        else:
            overflow = total - slot.max_lines

    layer = Image.new("RGBA", (slot.w, slot.h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    step = slot.font_size * slot.line_height
    for index, line in enumerate(lines):
        top = round(index * step)
        if top >= slot.h:
            break
        width = font.getlength(line)
        if slot.align == "left":
            x, anchor = 0.0, "la"
        elif slot.align == "center":
            x, anchor = (slot.w - width) / 2, "ma"
        else:
            x, anchor = slot.w - width, "ra"
        draw.text((x, top), line, font=font, fill=slot.color, anchor=anchor)
    canvas.paste(layer, (slot.x, slot.y), layer)
    return TextLayout(
        name=slot.name,
        total_lines=total,
        max_lines=slot.max_lines,
        dropped_lines=dropped,
        overflow_lines=overflow,
    )


class Renderer:
    """按模板槽位把一条素材画成成品图。"""

    def __init__(self, template: Template, font_path: str | Path):
        self.template = template
        self.font_path = Path(font_path)
        self._fonts: dict[int, ImageFont.FreeTypeFont] = {}
        self._font(1)  # 构造即校验字体，缺失立刻抛 FontMissing

    def _font(self, size: int) -> ImageFont.FreeTypeFont:
        size = int(size)
        if size not in self._fonts:
            self._fonts[size] = load_font(self.font_path, size)
        return self._fonts[size]

    def render(self, item: Item, image: Image.Image, truncate: bool = False) -> RenderResult:
        canvas = Image.new(
            "RGB",
            (self.template.canvas.width, self.template.canvas.height),
            self.template.canvas.background,
        )
        layouts: dict[str, TextLayout] = {}
        for slot in self.template.slots:
            if slot.type == "text":
                layout = _draw_text_slot(canvas, slot, slot_text(item, slot), self._font(slot.font_size), truncate)
                layouts[slot.name] = layout
            else:
                fitted = fit_image(image, slot.w, slot.h, slot.fit)
                fitted = round_corners(fitted, slot.radius)
                canvas.paste(fitted, (slot.x, slot.y), fitted)
        return RenderResult(image=canvas, layouts=layouts)


def save_png(image: Image.Image, path: Path, dpi: int) -> None:
    path = Path(path)
    image.convert("RGB").save(path, format="PNG", dpi=(dpi, dpi), optimize=True)


def save_pdf(images: list[Image.Image], path: Path, dpi: int) -> None:
    """整批写入一个 PDF；页面尺寸 = 画布像素 / dpi * 72。"""
    if not images:
        raise ValueError("没有可写入 PDF 的成品图")
    path = Path(path)
    pages = [image.convert("RGB") for image in images]
    first, rest = pages[0], pages[1:]
    first.save(path, format="PDF", resolution=dpi, save_all=True, append_images=rest)
