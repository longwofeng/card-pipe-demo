"""数据契约：Item / Slot / Template / Rule / Issue / Report。

字段名统一 snake_case；报告相关模型按固定顺序声明字段，diff 依赖这个顺序。
"""

from __future__ import annotations

import re
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_HEX = re.compile(r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _validate_hex(value: str) -> str:
    if not _HEX.match(value):
        raise ValueError(f"颜色必须是 #RGB 或 #RRGGBB，当前为 {value!r}")
    return value.upper()


class Item(_Model):
    """一条待生产的图文素材。"""

    id: str = Field(min_length=1)
    title: str = ""
    subtitle: str = ""
    body: str = ""
    bullets: list[str] = Field(default_factory=list)
    image: str = ""
    image_prompt: str = ""
    tags: list[str] = Field(default_factory=list)


class Canvas(_Model):
    width: int = Field(gt=0, le=10000)
    height: int = Field(gt=0, le=10000)
    background: str = "#FFFFFF"

    @field_validator("background")
    @classmethod
    def _check_background(cls, value: str) -> str:
        return _validate_hex(value)


class _Slot(_Model):
    name: str = Field(min_length=1)
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)


class TextSlot(_Slot):
    type: Literal["text"] = "text"
    font_size: int = Field(gt=0, le=400)
    line_height: float = Field(default=1.25, gt=0, le=5)
    color: str = "#111111"
    max_lines: int = Field(default=1, ge=1, le=50)
    align: Literal["left", "center", "right"] = "left"
    prefix: str | None = None

    @field_validator("color")
    @classmethod
    def _check_color(cls, value: str) -> str:
        return _validate_hex(value)


class ImageSlot(_Slot):
    type: Literal["image"] = "image"
    fit: Literal["cover", "contain"] = "cover"
    radius: int = Field(default=0, ge=0)


Slot = Annotated[Union[TextSlot, ImageSlot], Field(discriminator="type")]


class Template(_Model):
    canvas: Canvas
    slots: list[Slot] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_slot_names(self) -> "Template":
        names = [slot.name for slot in self.slots]
        duplicated = sorted({name for name in names if names.count(name) > 1})
        if duplicated:
            raise ValueError(f"槽位 name 必须唯一，重复：{duplicated}")
        return self


class Limits(_Model):
    title_chars: int = Field(gt=0)
    subtitle_chars: int = Field(gt=0)
    body_chars: int = Field(gt=0)
    bullets_max: int = Field(gt=0)


class ImageLimits(_Model):
    min_width: int = Field(gt=0)
    min_height: int = Field(gt=0)
    ratio_tolerance: float = Field(ge=0)


class OutputConfig(_Model):
    png_dpi: int = Field(default=144, gt=0)
    pdf: bool = True


class Rule(_Model):
    limits: Limits
    image: ImageLimits
    on_violation: Literal["report", "truncate", "fail"] = "report"
    output: OutputConfig = Field(default_factory=OutputConfig)


class Issue(_Model):
    code: str
    field: str
    message: str
    severity: Literal["error", "warning", "info"] = "error"


class ReportItem(_Model):
    id: str
    status: Literal["ok", "ok_with_issues", "truncated", "failed"] = "ok"
    chars: dict[str, int] = Field(default_factory=dict)
    image: dict[str, int] = Field(default_factory=dict)
    issues: list[Issue] = Field(default_factory=list)
    ms: int = 0


class Report(_Model):
    batch: str
    total: int = 0
    ok: int = 0
    violations: int = 0
    items: list[ReportItem] = Field(default_factory=list)
