"""可选 HTTP 入口（FastAPI）：POST /build、GET /out/{batch}/{file}。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ValidationError

from .cli import ROOT, InputError, build_batch, load_items
from .materials import MaterialError
from .models import Item, Rule, Template
from .render import FontMissing, TemplateError, load_template
from .report import report_dict
from .rules import RuleLoadError, load_rules

OUT_ROOT = ROOT / "out"

app = FastAPI(title="图文自动化生产管线 CardPipe", version="1.0.0")


class BuildRequest(BaseModel):
    items: Any
    template: Any = None
    rules: Any = None
    provider: Literal["local", "mock", "api"] = "local"


class BuildResponse(BaseModel):
    batch_id: str
    report: dict
    files: list[str]


def _resolve(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _items_from(spec: Any) -> list[Item]:
    if isinstance(spec, str):
        return load_items(_resolve(spec))
    if isinstance(spec, dict):
        spec = spec.get("items")
    if isinstance(spec, list):
        if not spec:
            raise InputError("items 不能为空")
        return [Item.model_validate(entry) for entry in spec]
    raise InputError("items 需要是文件路径、条目数组或 {items: [...]}")


def _template_from(spec: Any) -> Template:
    if spec is None:
        return load_template(ROOT / "templates" / "card_a.json")
    if isinstance(spec, str):
        return load_template(_resolve(spec))
    if isinstance(spec, dict):
        return Template.model_validate(spec)
    raise InputError("template 需要是文件路径或模板对象")


def _rules_from(spec: Any) -> Rule:
    if spec is None:
        return load_rules(ROOT / "rules.yaml")
    if isinstance(spec, str):
        return load_rules(_resolve(spec))
    if isinstance(spec, dict):
        return Rule.model_validate(spec)
    raise InputError("rules 需要是文件路径或规则对象")


@app.post("/build", response_model=BuildResponse)
def build(request: BuildRequest) -> BuildResponse:
    try:
        items = _items_from(request.items)
        template = _template_from(request.template)
        rule = _rules_from(request.rules)
    except (InputError, TemplateError, RuleLoadError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    canonical = json.dumps(
        {
            "items": [item.model_dump() for item in items],
            "template": template.model_dump(),
            "rules": rule.model_dump(),
            "provider": request.provider,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    batch_id = "api_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    out_dir = OUT_ROOT / batch_id
    try:
        outcome = build_batch(
            items,
            template,
            rule,
            out_dir,
            provider=request.provider,
            batch_name=batch_id,
        )
    except FontMissing as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except MaterialError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    files = sorted(path.name for path in out_dir.glob("*") if path.is_file())
    return BuildResponse(batch_id=batch_id, report=report_dict(outcome.report), files=files)


@app.get("/out/{batch}/{name}")
def get_output(batch: str, name: str) -> FileResponse:
    target = (OUT_ROOT / batch / name).resolve()
    if not target.is_relative_to(OUT_ROOT.resolve()) or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(target)

