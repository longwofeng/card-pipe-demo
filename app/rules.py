"""规则加载与校验；本模块只做判定，不渲染、不写文件。"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import Issue, Item, Rule, Template

TEXT_FIELDS = ("title", "subtitle", "body")
TEXT_CODES = {"title_too_long", "subtitle_too_long", "body_too_long", "too_many_bullets"}
FIELD_LABELS = {"title": "标题", "subtitle": "副标题", "body": "正文", "bullets": "要点"}


class RuleLoadError(ValueError):
    """规则文件缺失或格式错误。"""


def load_rules(path: Path) -> Rule:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuleLoadError(f"读取规则失败 {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise RuleLoadError(f"规则不是合法 YAML {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise RuleLoadError(f"规则根节点必须是映射（mapping）：{path}")
    try:
        return Rule.model_validate(raw)
    except ValidationError as exc:
        raise RuleLoadError(f"规则字段错误 {path}:\n{exc}") from exc


def char_counts(item: Item) -> dict[str, int]:
    """按模板无关的固定顺序统计字数，供报告使用。"""
    return {
        "title": len(item.title),
        "subtitle": len(item.subtitle),
        "body": len(item.body),
        "bullets": sum(len(bullet) for bullet in item.bullets),
    }


def check_text(item: Item, rule: Rule) -> list[Issue]:
    """字数与要点条数校验：恰好等于上限不报，超 1 即报。"""
    limits = rule.limits
    plan = (
        ("title", limits.title_chars, "title_too_long"),
        ("subtitle", limits.subtitle_chars, "subtitle_too_long"),
        ("body", limits.body_chars, "body_too_long"),
    )
    issues: list[Issue] = []
    for field, limit, code in plan:
        length = len(getattr(item, field))
        if length > limit:
            issues.append(
                Issue(
                    code=code,
                    field=field,
                    message=f"{FIELD_LABELS[field]} {length} 字，超过上限 {limit}",
                    severity="error",
                )
            )
    if len(item.bullets) > limits.bullets_max:
        issues.append(
            Issue(
                code="too_many_bullets",
                field="bullets",
                message=f"{FIELD_LABELS['bullets']} {len(item.bullets)} 条，超过上限 {limits.bullets_max}",
                severity="error",
            )
        )
    return issues


def _slot_text(item: Item, name: str) -> list[str] | None:
    if name in TEXT_FIELDS:
        value = getattr(item, name)
        return [value] if value else None
    if name == "bullets":
        return [bullet for bullet in item.bullets if bullet] or None
    return None


def check_missing(item: Item, template: Template) -> list[Issue]:
    """模板里有文字槽位，但素材对应字段为空。"""
    issues: list[Issue] = []
    for slot in template.slots:
        if slot.type != "text":
            continue
        if _slot_text(item, slot.name) is None:
            issues.append(
                Issue(
                    code="missing_field",
                    field=slot.name,
                    message=f"槽位 {slot.name} 缺少内容",
                    severity="error",
                )
            )
    return issues


def check_image(meta: dict, rule: Rule, template: Template) -> list[Issue]:
    """图片实际宽高与比例校验（比例对比槽位比例）。"""
    width = int(meta.get("w") or 0)
    height = int(meta.get("h") or 0)
    if width <= 0 or height <= 0:
        return [Issue(code="missing_field", field="image", message="图片缺失或尺寸为 0", severity="error")]
    issues: list[Issue] = []
    limits = rule.image
    if width < limits.min_width or height < limits.min_height:
        issues.append(
            Issue(
                code="image_too_small",
                field="image",
                message=f"图片 {width}x{height} 小于下限 {limits.min_width}x{limits.min_height}",
                severity="error",
            )
        )
    slot = next((slot for slot in template.slots if slot.type == "image"), None)
    if slot is not None and slot.h > 0:
        image_ratio = width / height
        slot_ratio = slot.w / slot.h
        if abs(image_ratio - slot_ratio) > limits.ratio_tolerance:
            issues.append(
                Issue(
                    code="image_ratio_off",
                    field="image",
                    message=(
                        f"图片宽高比 {image_ratio:.3f} 与槽位 {slot_ratio:.3f} "
                        f"相差 {abs(image_ratio - slot_ratio):.3f}，超出容差 {limits.ratio_tolerance}"
                    ),
                    severity="error",
                )
            )
    return issues


def validate_item(item: Item, rule: Rule, template: Template, image_meta: dict) -> list[Issue]:
    """完整校验：文字 → 缺字段 → 图片，顺序固定，便于 diff。"""
    return check_text(item, rule) + check_missing(item, template) + check_image(image_meta, rule, template)


def truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 0:
        return ""
    if limit == 1:
        return "…"
    return text[: limit - 1] + "…"


def truncate_item(item: Item, rule: Rule) -> tuple[Item, list[Issue]]:
    """按规则截断文本与要点，返回新 item 与 truncated 记录。"""
    data = item.model_dump()
    issues: list[Issue] = []
    plan = (
        ("title", rule.limits.title_chars),
        ("subtitle", rule.limits.subtitle_chars),
        ("body", rule.limits.body_chars),
    )
    for field, limit in plan:
        original = data[field]
        if len(original) > limit:
            data[field] = truncate_text(original, limit)
            issues.append(
                Issue(
                    code="truncated",
                    field=field,
                    message=f"{FIELD_LABELS[field]} {len(original)} 字超过 {limit}，已截断并重新排版",
                    severity="warning",
                )
            )
    if len(data["bullets"]) > rule.limits.bullets_max:
        dropped = len(data["bullets"]) - rule.limits.bullets_max
        data["bullets"] = data["bullets"][: rule.limits.bullets_max]
        issues.append(
            Issue(
                code="truncated",
                field="bullets",
                message=f"要点超过 {rule.limits.bullets_max} 条，已删除末尾 {dropped} 条",
                severity="warning",
            )
        )
    return Item.model_validate(data), issues
