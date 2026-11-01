"""命令行入口：build / demo / selfcheck。

build 是唯一的生产入口，demo 与 api 复用同一个 build_batch。
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import yaml
from PIL import Image, ImageDraw
from pydantic import ValidationError

from .materials import ApiProvider, LocalProvider, MaterialError, MockProvider
from .models import Issue, Item, Report, ReportItem, Rule, Template
from .render import FontMissing, Renderer, TemplateError, load_font, load_template, resolve_font_path, save_pdf, save_png
from .report import PDF_FILE, diff_markdown, diff_reports, issue_counts, report_dict, write_manifest, write_report
from .rules import (
    TEXT_CODES,
    RuleLoadError,
    char_counts,
    load_rules,
    truncate_item,
    validate_item,
)

ROOT = Path(__file__).resolve().parents[1]

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_VIOLATION = 2
EXIT_FONT = 3
EXIT_INPUT = 4

DEFAULT_ITEMS = ROOT / "data" / "items.yaml"
DEFAULT_TEMPLATE = ROOT / "templates" / "card_a.json"
DEFAULT_RULES = ROOT / "rules.yaml"


class InputError(ValueError):
    """输入数据格式错误（退出码 4）。"""


@dataclass
class BuildOutcome:
    report: Report
    out_dir: Path
    produced: bool


def load_items(path: Path) -> list[Item]:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise InputError(f"读取 items 失败 {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise InputError(f"items 不是合法 YAML {path}: {exc}") from exc
    if isinstance(raw, dict):
        raw = raw.get("items")
    if not isinstance(raw, list) or not raw:
        raise InputError(f"items 必须是非空列表（或 {{items: [...]}}）：{path}")
    try:
        items = [Item.model_validate(entry) for entry in raw]
    except ValidationError as exc:
        raise InputError(f"items 字段错误 {path}:\n{exc}") from exc
    ids = [item.id for item in items]
    duplicated = sorted({item_id for item_id in ids if ids.count(item_id) > 1})
    if duplicated:
        raise InputError(f"items.id 必须唯一，重复：{duplicated}")
    return items


def make_provider(kind: str, rule: Rule, template: Template):
    slot = next((slot for slot in template.slots if slot.type == "image"), None)
    slot_ratio = slot.w / slot.h if slot is not None else None
    local = LocalProvider(ROOT, rule.image.min_width, rule.image.min_height, slot_ratio)
    if kind == "local":
        return local
    if kind == "mock":
        return MockProvider(rule.image.min_width, rule.image.min_height)
    if kind == "api":
        return ApiProvider(local)
    raise InputError(f"未知 provider：{kind}")


def _image_dict(meta: dict) -> dict[str, int]:
    return {"w": int(meta.get("w") or 0), "h": int(meta.get("h") or 0)}


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


def _status(issues: list[Issue]) -> str:
    if any(issue.code == "truncated" for issue in issues):
        return "truncated"
    if issues:
        return "ok_with_issues"
    return "ok"


def build_batch(
    items: list[Item],
    template: Template,
    rule: Rule,
    out_dir: Path,
    provider: str = "local",
    font_path: str | Path | None = None,
    batch_name: str | None = None,
) -> BuildOutcome:
    """生产一批成品；on_violation=fail 且有条目违规时整批不产出。"""
    out_dir = Path(out_dir)
    renderer = Renderer(template, resolve_font_path(font_path))
    material = make_provider(provider, rule, template)
    report = Report(batch=batch_name or out_dir.name, total=len(items))
    produced = True
    pending_png: list[tuple[Path, Image.Image]] = []
    pages: list[Image.Image] = []

    for item in items:
        started = time.perf_counter()
        image, meta = material.resolve(item)
        issues = validate_item(item, rule, template, meta)
        if meta.get("fallback"):
            issues.append(Issue(code="fallback", field="image", message=f"fallback: {meta['fallback']}", severity="info"))

        rendered_item = item
        if rule.on_violation == "truncate" and any(issue.code in TEXT_CODES for issue in issues):
            rendered_item, truncated = truncate_item(item, rule)
            issues = [issue for issue in issues if issue.code not in TEXT_CODES] + truncated

        if rule.on_violation == "fail" and any(issue.severity == "error" for issue in issues):
            produced = False
            report.items.append(
                ReportItem(
                    id=item.id,
                    status="failed",
                    chars=char_counts(item),
                    image=_image_dict(meta),
                    issues=issues,
                    ms=_elapsed_ms(started),
                )
            )
            continue

        result = renderer.render(rendered_item, image, truncate=rule.on_violation == "truncate")
        for layout in result.layouts.values():
            if rule.on_violation == "truncate" and layout.dropped_lines:
                issues.append(
                    Issue(
                        code="truncated",
                        field=layout.name,
                        message=f"排版 {layout.total_lines} 行超过槽位 {layout.max_lines} 行，已截断 {layout.dropped_lines} 行",
                        severity="warning",
                    )
                )
            elif rule.on_violation != "truncate" and layout.overflow_lines:
                issues.append(
                    Issue(
                        code="text_overflow",
                        field=layout.name,
                        message=f"排版 {layout.total_lines} 行超过槽位 {layout.max_lines} 行，已按槽位裁剪",
                        severity="warning",
                    )
                )

        report.items.append(
            ReportItem(
                id=item.id,
                status=_status(issues),
                chars=char_counts(rendered_item),
                image=_image_dict(meta),
                issues=issues,
                ms=_elapsed_ms(started),
            )
        )
        if produced:
            pending_png.append((out_dir / f"{item.id}.png", result.image))
            pages.append(result.image)

    report.total = len(items)
    report.violations = sum(
        1 for entry in report.items if any(issue.severity == "error" for issue in entry.issues)
    )
    report.ok = report.total - report.violations

    out_dir.mkdir(parents=True, exist_ok=True)
    if produced:
        for path, image in pending_png:
            save_png(image, path, rule.output.png_dpi)
        if rule.output.pdf and pages:
            save_pdf(pages, out_dir / PDF_FILE, rule.output.png_dpi)
        write_manifest(report, out_dir)
    write_report(report, out_dir)
    return BuildOutcome(report=report, out_dir=out_dir, produced=produced)


def _print_build_summary(outcome: BuildOutcome, rule: Rule, elapsed: float) -> None:
    report = outcome.report
    failed = sum(1 for entry in report.items if entry.status == "failed")
    print(f"处理条数: {report.total}")
    print(f"失败条数: {failed}")
    print(f"违规条数: {report.violations}")
    print(f"输出目录: {outcome.out_dir.resolve()}")
    print(f"耗时: {elapsed:.3f}s")
    if not outcome.produced:
        print("[FAIL] on_violation=fail 且存在违规，整批未产出；违规明细见 report.json")
    else:
        print(
            f"[OK] PNG {report.total} 张"
            f"{'，PDF 1 份' if rule.output.pdf else ''}"
            f"，report.json / manifest.csv 已写入"
        )


def cmd_build(args: argparse.Namespace) -> int:
    items_path = Path(args.items)
    template_path = Path(args.template)
    rules_path = Path(args.rules)
    items = load_items(items_path)
    template = load_template(template_path)
    rule = load_rules(rules_path)
    started = time.perf_counter()
    outcome = build_batch(
        items,
        template,
        rule,
        Path(args.out),
        provider=args.provider,
        font_path=args.font,
    )
    elapsed = time.perf_counter() - started
    _print_build_summary(outcome, rule, elapsed)
    return EXIT_OK if outcome.produced else EXIT_VIOLATION


def _produced_all(outcome: BuildOutcome, items: list[Item], pdf_required: bool = True) -> bool:
    if not outcome.produced:
        return False
    if any(not (outcome.out_dir / f"{item.id}.png").is_file() for item in items):
        return False
    if pdf_required and not (outcome.out_dir / PDF_FILE).is_file():
        return False
    return True


def cmd_demo(args: argparse.Namespace) -> int:
    out_root = Path(args.out)
    items_path = Path(args.items)
    template_path = Path(args.template)
    rules_path = Path(args.rules)
    items = load_items(items_path)
    template = load_template(template_path)
    rule1 = load_rules(rules_path)

    with tempfile.TemporaryDirectory(prefix="cardpipe_rules_") as tmp:
        raw = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise InputError(f"规则根节点必须是映射：{rules_path}")
        raw.setdefault("limits", {})
        raw["limits"]["title_chars"] = 12
        rule2_path = Path(tmp) / "rules.yaml"
        rule2_path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
        rule2 = load_rules(rule2_path)
        if rule1.limits.title_chars == 12:
            print("[WARN] 仓库 rules.yaml 的 title_chars 已经是 12，第一遍就会产生违规，demo 无法通过")

        print(f"[demo] 第一遍：{rules_path}（title_chars={rule1.limits.title_chars}）")
        print(f"[demo] 第二遍：临时副本（title_chars={rule2.limits.title_chars}，未改动仓库 rules.yaml）")

        outcome1 = build_batch(
            items, template, rule1, out_root / "run1", provider=args.provider, font_path=args.font, batch_name="run1"
        )
        outcome2 = build_batch(
            items, template, rule2, out_root / "run2", provider=args.provider, font_path=args.font, batch_name="run2"
        )

    report1 = report_dict(outcome1.report)
    report2 = report_dict(outcome2.report)
    diff = diff_reports(report1, report2)

    out_root.mkdir(parents=True, exist_ok=True)
    diff_json = out_root / "report_diff.json"
    diff_md = out_root / "report_diff.md"
    diff_json.write_text(json.dumps(diff, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    diff_md.write_text(diff_markdown(diff), encoding="utf-8")

    count1 = issue_counts(report1).get("title_too_long", 0)
    count2 = issue_counts(report2).get("title_too_long", 0)
    produced1 = _produced_all(outcome1, items)
    produced2 = _produced_all(outcome2, items)

    for name, report, produced in (("第一遍", report1, produced1), ("第二遍", report2, produced2)):
        print(
            f"[demo] {name}: total={report['total']} ok={report['ok']} "
            f"violations={report['violations']} — {PRODUCED_TEXT if produced else NOT_PRODUCED_TEXT}"
        )
    print()
    print("[demo] 两次报告差异：")
    print(diff_markdown(diff))
    print(f"[demo] 差异明细：{diff_json}")
    print(f"[demo] 差异表：{diff_md}")
    print()

    checks = [
        (count1 == 0, f"第一遍 title_too_long = {count1}（要求 0）"),
        (count2 >= 1, f"第二遍 title_too_long = {count2}（要求 >= 1）"),
        (produced1, "第一遍产出 PNG 与 batch.pdf"),
        (produced2, "第二遍产出 PNG 与 batch.pdf"),
        (diff.get("changed", False), "两次报告存在差异"),
    ]
    for ok, label in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    passed = all(ok for ok, _ in checks)
    print()
    print("PASS" if passed else "FAIL")
    return EXIT_OK if passed else EXIT_FAIL


PRODUCED_TEXT = "PNG + PDF 已产出"
NOT_PRODUCED_TEXT = "未产出"


def _ink_ratio(font, text: str = "低空政务巡查智能体") -> float:
    canvas = Image.new("RGB", (560, 120), (255, 255, 255))
    ImageDraw.Draw(canvas).text((8, 12), text, font=font, fill=(0, 0, 0))
    pixels = canvas.load()
    inked = 0
    total = canvas.width * canvas.height
    for y in range(canvas.height):
        for x in range(canvas.width):
            if pixels[x, y] != (255, 255, 255):
                inked += 1
    return inked / total


def _asset_provenance() -> tuple[bool, str, str]:
    """人物素材授权登记：目录里每张图都必须在 SOURCES.md 里登记。"""
    people_dir = ROOT / "assets" / "images" / "people"
    if not people_dir.is_dir():
        return True, "人物素材授权登记", "未启用人物素材目录，跳过"
    manifest = people_dir / "SOURCES.md"
    suffixes = {".png", ".jpg", ".jpeg", ".webp"}
    files = sorted(path.name for path in people_dir.iterdir() if path.suffix.lower() in suffixes)
    if not files:
        return True, "人物素材授权登记", "目录为空，跳过"
    if not manifest.is_file():
        return False, "人物素材授权登记", f"缺少 {manifest.name}"
    text = manifest.read_text(encoding="utf-8")
    missing = [name for name in files if name not in text]
    if missing:
        return False, "人物素材授权登记", f"未登记来源：{', '.join(missing)}"
    return True, "人物素材授权登记", f"{len(files)} 张图已登记（自制或已授权）"


def cmd_selfcheck(args: argparse.Namespace) -> int:
    checks: list[tuple[bool, str, str]] = []

    def add(ok: bool, label: str, detail: str = "") -> None:
        checks.append((ok, label, detail))

    version = ".".join(str(part) for part in sys.version_info[:3])
    add(sys.version_info >= (3, 11), f"Python {version}", "需要 3.11+")

    font_path = resolve_font_path(getattr(args, "font", None))
    add(font_path.is_file(), f"字体文件 {font_path.relative_to(ROOT) if font_path.is_relative_to(ROOT) else font_path}", "缺少中文字体时会直接退出（退出码 3）")
    if font_path.is_file():
        try:
            font = load_font(font_path, 48)
            ratio = _ink_ratio(font)
            name = font.getname()
            add(ratio > 0.05, f"中文字形可渲染（{name[0]} {name[1]}）", f"抽样非背景像素 {ratio:.1%}，阈值 5%")
        except FontMissing as exc:
            add(False, "字体可加载", str(exc))
    else:
        add(False, "中文字形可渲染", "字体文件不存在，未做渲染抽样")

    try:
        items = load_items(DEFAULT_ITEMS)
        add(True, f"样例数据 {DEFAULT_ITEMS.relative_to(ROOT)}", f"{len(items)} 条，id 唯一")
    except (InputError, OSError) as exc:
        add(False, f"样例数据 {DEFAULT_ITEMS.relative_to(ROOT)}", str(exc))

    try:
        template = load_template(DEFAULT_TEMPLATE)
        text_slots = sum(1 for slot in template.slots if slot.type == "text")
        image_slots = sum(1 for slot in template.slots if slot.type == "image")
        add(True, f"模板 {DEFAULT_TEMPLATE.relative_to(ROOT)}", f"{template.canvas.width}x{template.canvas.height}，文字槽位 {text_slots}，图片槽位 {image_slots}")
    except (TemplateError, OSError) as exc:
        add(False, f"模板 {DEFAULT_TEMPLATE.relative_to(ROOT)}", str(exc))

    try:
        rule = load_rules(DEFAULT_RULES)
        add(True, f"规则 {DEFAULT_RULES.relative_to(ROOT)}", f"on_violation={rule.on_violation}，png_dpi={rule.output.png_dpi}，pdf={rule.output.pdf}")
    except (RuleLoadError, OSError) as exc:
        add(False, f"规则 {DEFAULT_RULES.relative_to(ROOT)}", str(exc))

    provenance_ok, provenance_label, provenance_detail = _asset_provenance()
    add(provenance_ok, provenance_label, provenance_detail)

    probe_dir = ROOT / "out" / ".selfcheck"
    try:
        probe_dir.mkdir(parents=True, exist_ok=True)
        probe_file = probe_dir / "probe.txt"
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink()
        probe_dir.rmdir()
        add(True, "输出目录可写 out/", "创建与删除探针文件成功")
    except OSError as exc:
        add(False, "输出目录可写 out/", str(exc))

    print("自检清单：")
    for ok, label, detail in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {label}" + (f" —— {detail}" if detail else ""))
    failed = [label for ok, label, _ in checks if not ok]
    print()
    if failed:
        print(f"自检未通过：{len(failed)} 项失败")
        return EXIT_FAIL
    print(f"自检通过：{len(checks)} 项全部 OK")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="批量图文生产管线（CardPipe）")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser_ = subparsers.add_parser("build", help="按模板与规则批量出图")
    build_parser_.add_argument("--items", required=True, help="items.yaml 路径")
    build_parser_.add_argument("--template", required=True, help="模板 JSON 路径")
    build_parser_.add_argument("--rules", required=True, help="规则 YAML 路径")
    build_parser_.add_argument("--out", required=True, help="输出目录")
    build_parser_.add_argument("--provider", choices=["local", "mock", "api"], default="local", help="素材来源，默认 local")
    build_parser_.add_argument("--font", default=None, help="可选：覆盖字体路径")

    demo_parser = subparsers.add_parser("demo", help="改一条规则重跑并对比报告")
    demo_parser.add_argument("--out", default="out/acceptance", help="输出目录，默认 out/acceptance")
    demo_parser.add_argument("--items", default=str(DEFAULT_ITEMS))
    demo_parser.add_argument("--template", default=str(DEFAULT_TEMPLATE))
    demo_parser.add_argument("--rules", default=str(DEFAULT_RULES))
    demo_parser.add_argument("--provider", choices=["local", "mock", "api"], default="local")
    demo_parser.add_argument("--font", default=None, help="可选：覆盖字体路径")

    selfcheck_parser = subparsers.add_parser("selfcheck", help="检查字体、样例数据、模板、规则与输出权限")
    selfcheck_parser.add_argument("--font", default=None, help="可选：覆盖字体路径")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "build":
            return cmd_build(args)
        if args.command == "demo":
            return cmd_demo(args)
        return cmd_selfcheck(args)
    except FontMissing as exc:
        print(f"[FONT] {exc}", file=sys.stderr)
        print("提示：字体是硬依赖，缺失即退出码 3，不会画出方块。", file=sys.stderr)
        return EXIT_FONT
    except (InputError, TemplateError, RuleLoadError) as exc:
        print(f"[INPUT] {exc}", file=sys.stderr)
        return EXIT_INPUT
    except MaterialError as exc:
        print(f"[INPUT] {exc}", file=sys.stderr)
        return EXIT_INPUT
    except KeyboardInterrupt:
        print("[ABORT] 已中断", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())




