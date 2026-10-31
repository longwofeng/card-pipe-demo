"""素材提供者：LocalProvider / MockProvider / ApiProvider。

三个实现都满足同一个 MaterialProvider 协议：``resolve(item) -> (PIL.Image, meta)``。
所有随机/配色都由稳定 hash 推导，保证同输入同输出。
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import os
import urllib.request
from pathlib import Path
from typing import Protocol, runtime_checkable

from PIL import Image, ImageDraw, ImageOps

from .models import Item


class MaterialError(RuntimeError):
    """素材读取失败（文件存在但无法解码等）。"""


@runtime_checkable
class MaterialProvider(Protocol):
    def resolve(self, item: Item) -> tuple[Image.Image, dict]: ...


def _stable_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _seed(text: str) -> int:
    return int(_stable_digest(text)[:8], 16)


def _palette(seed: int) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    r1, g1, b1 = 40 + seed % 120, 60 + (seed >> 8) % 120, 90 + (seed >> 16) % 120
    r2, g2, b2 = min(r1 + 70, 235), min(g1 + 60, 235), min(b1 + 50, 235)
    return (r1, g1, b1), (r2, g2, b2)


def load_image_file(path: Path) -> Image.Image:
    """按 EXIF 方向纠正后读入 RGB 图。"""
    try:
        with Image.open(path) as raw:
            image = ImageOps.exif_transpose(raw).convert("RGB")
    except OSError as exc:  # 解码失败统一抛素材错误，由 CLI 映射为输入错误
        raise MaterialError(f"无法读取图片 {path}: {exc}") from exc
    return image


def placeholder_size(min_width: int, min_height: int, slot_ratio: float | None) -> tuple[int, int]:
    """占位图尺寸：不低于 image.min_*，并尽量贴合图片槽位比例。"""
    if not slot_ratio or slot_ratio <= 0:
        return max(min_width, 1), max(min_height, 1)
    height = max(min_height, 1)
    width = max(min_width, math.ceil(height * slot_ratio))
    # 让宽高比严格落在目标比例上（向下取整带来的偏差在此修正）
    while width / height > slot_ratio:
        height += 1
    while width / height < slot_ratio:
        width += 1
    return width, height


def _draw_placeholder(width: int, height: int, seed: int) -> Image.Image:
    (r1, g1, b1), (r2, g2, b2) = _palette(seed)
    image = Image.new("RGB", (width, height), (r1, g1, b1))
    draw = ImageDraw.Draw(image)
    # 上浅下深的柔和渐变，避免纯色占位图看起来像加载失败
    for y in range(height):
        t = y / max(height - 1, 1)
        draw.line(
            [(0, y), (width, y)],
            fill=(round(r1 + (r2 - r1) * t), round(g1 + (g2 - g1) * t), round(b1 + (b2 - b1) * t)),
        )
    # 固定几何装饰（由 seed 决定位置，无随机数）
    cx = int(width * (0.3 + (seed % 40) / 100))
    cy = int(height * (0.4 + ((seed >> 5) % 20) / 100))
    radius = int(min(width, height) * 0.18)
    draw.ellipse(
        [(cx - radius, cy - radius), (cx + radius, cy + radius)],
        fill=(min(r2 + 20, 255), min(g2 + 20, 255), min(b2 + 20, 255)),
    )
    return image


class LocalProvider:
    """本地素材：item.image 存在就读，不存在生成占位图。"""

    def __init__(self, root: Path, min_width: int = 800, min_height: int = 800, slot_ratio: float | None = None):
        self.root = Path(root)
        self.min_width = min_width
        self.min_height = min_height
        self.slot_ratio = slot_ratio

    def resolve(self, item: Item) -> tuple[Image.Image, dict]:
        if item.image:
            path = Path(item.image)
            if not path.is_absolute():
                path = self.root / path
            if path.is_file():
                image = load_image_file(path)
                return image, {"w": image.width, "h": image.height, "source": "local"}
        width, height = placeholder_size(self.min_width, self.min_height, self.slot_ratio)
        image = _draw_placeholder(width, height, _seed(item.id))
        return image, {"w": width, "h": height, "source": "placeholder"}


class MockProvider:
    """测试用：按稳定 hash 生成纯色图，尺寸取 image.min_*。"""

    def __init__(self, min_width: int = 800, min_height: int = 800):
        self.min_width = max(min_width, 1)
        self.min_height = max(min_height, 1)

    def resolve(self, item: Item) -> tuple[Image.Image, dict]:
        (r, g, b), _ = _palette(_seed(item.id))
        image = Image.new("RGB", (self.min_width, self.min_height), (r, g, b))
        return image, {"w": self.min_width, "h": self.min_height, "source": "mock"}


class ApiProvider:
    """按 image_prompt 调远端图片接口；任何异常都回退 LocalProvider。"""

    def __init__(self, fallback: LocalProvider, base_url: str | None = None, api_key: str | None = None, model: str | None = None, timeout: float = 20.0):
        self.fallback = fallback
        self.base_url = (base_url if base_url is not None else os.environ.get("OPENAI_BASE_URL", "")).rstrip("/")
        self.api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
        self.model = model if model is not None else os.environ.get("MODEL_NAME", "")
        self.timeout = timeout

    def available(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def resolve(self, item: Item) -> tuple[Image.Image, dict]:
        if not self.available():
            image, meta = self.fallback.resolve(item)
            meta = dict(meta, fallback="api_unavailable")
            return image, meta
        try:
            image = self._generate(item)
        except Exception:  # 网络/鉴权/解析任何异常都回退，保证批量任务不中断
            image, meta = self.fallback.resolve(item)
            meta = dict(meta, fallback="api_unavailable")
            return image, meta
        return image, {"w": image.width, "h": image.height, "source": "api"}

    def _generate(self, item: Item) -> Image.Image:
        payload = {
            "model": self.model,
            "prompt": item.image_prompt or item.title,
            "size": "1024x1024",
            "response_format": "b64_json",
        }
        request = urllib.request.Request(
            f"{self.base_url}/images/generations",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        entry = data["data"][0]
        if entry.get("b64_json"):
            raw = base64.b64decode(entry["b64_json"])
        elif entry.get("url"):
            with urllib.request.urlopen(entry["url"], timeout=self.timeout) as response:
                raw = response.read()
        else:
            raise MaterialError("接口未返回 b64_json 或 url")
        return Image.open(io.BytesIO(raw)).convert("RGB")
