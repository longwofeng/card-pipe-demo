# 图文自动化 Demo · CardPipe

> 一句话：把「一批素材 + 一套模板 + 一份规则」变成一条**可批量运行、可改规则重跑**的图文生产线。
> 目标不是炫技，是让人在两分钟内看到四件事：模板能拆、素材能换、成品能出、规则能改。

---

## 1. 演示要验证的四件事

| 要验证的能力 | 本 Demo 的落点 |
|---|---|
| 图文模板拆解 | `templates/card_a.json` 用槽位描述版式，渲染器按槽位排版；换模板不用改代码 |
| 素材替换 | 素材目录 + `MaterialProvider`（local / mock / api 三种实现） |
| 排版输出 | 输出 PNG（单张）与 PDF（整批），字体、尺寸、留白由模板约束 |
| 规则校验 + 可重跑 | `rules.yaml` 驱动校验，`report.json` 记录；改一条规则重跑，结果可复现 |

---

## 2. 快速开始（三条命令）

```
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m app.cli build --items data/items.yaml --template templates/card_a.json --rules rules.yaml --out out/demo1
```

看结果：
- `out/demo1/item_001.png` —— 成品图
- `out/demo1/report.json` —— 校验明细（字数、图片尺寸、耗时）
- `out/demo1/batch.pdf` —— 整批合成 PDF

一条命令跑完「改规则 → 重跑 → 对比报告」的验收动作：

```
python -m app.cli demo --out out/acceptance
```

输出 `PASS/FAIL` 和两次报告的差异表。

---

## 3. 目录结构

```
app/
  cli.py          # 命令行入口：build / demo / selfcheck
  api.py          # 可选 HTTP 入口（FastAPI）
  models.py       # Item / Template / Slot / Rule / Report 数据结构
  render.py       # 模板解析 + 排版 + PNG/PDF 导出
  materials.py    # 素材选择与生成（local / mock / api）
  rules.py        # 规则加载与校验
  report.py       # 报告与清单输出
templates/card_a.json
data/items.yaml
assets/fonts/NotoSansSC-Regular.ttf   # 必须自带，否则中文全是方块
assets/images/                        # 测试素材
rules.yaml
tests/
out/
```

---

## 4. 输入规格 `data/items.yaml`

```
items:
  - id: item_001
    title: 春季新品上市
    subtitle: 轻量 · 透气 · 三色可选
    body: 这是一段正文，描述产品的核心卖点与适用场景。
    bullets:
      - 三层透气网布
      - 单只 180g
    image: assets/images/a.jpg
    image_prompt: 纯白背景，产品居中，柔和侧光
    tags: [promo]
```

- `id` 唯一，用于输出文件名与报告定位
- 文本字段与模板槽位名一一对应，缺字段即触发校验
- `image` 为空时走 `MaterialProvider` 生成或占位

---

## 5. 模板规格 `templates/card_a.json`

```
{
  "canvas": { "width": 1080, "height": 1440, "background": "#FFFFFF" },
  "slots": [
    { "type": "text",  "name": "title",    "x": 80, "y": 120,  "w": 920, "h": 200,
      "font_size": 64, "line_height": 1.25, "color": "#111111", "max_lines": 2, "align": "left" },
    { "type": "text",  "name": "subtitle", "x": 80, "y": 340,  "w": 920, "h": 80,
      "font_size": 34, "line_height": 1.3,  "color": "#666666", "max_lines": 1, "align": "left" },
    { "type": "image", "name": "hero",     "x": 80, "y": 460,  "w": 920, "h": 720,
      "fit": "cover", "radius": 24 },
    { "type": "text",  "name": "bullets",  "x": 80, "y": 1210, "w": 920, "h": 160,
      "font_size": 30, "line_height": 1.4, "color": "#222222", "max_lines": 4, "align": "left",
      "prefix": "· " }
  ]
}
```

槽位类型只有两种，够用且好讲：`text`（换行、行高、对齐、最大行数）与 `image`（cover/contain、圆角）。

---

## 6. 规则 `rules.yaml`

```
limits:
  title_chars: 18
  subtitle_chars: 24
  body_chars: 120
  bullets_max: 4
image:
  min_width: 800
  min_height: 800
  ratio_tolerance: 0.15
on_violation: report        # report | truncate | fail
output:
  png_dpi: 144
  pdf: true
```

- `on_violation: report`：照常出图，问题进报告（验收默认）
- `truncate`：超字数自动截断并标红报告
- `fail`：任一违规即整批退出（退出码 2）

---

## 7. 输出物

```
out/<batch>/
  item_001.png
  batch.pdf
  report.json     # 每条：字数、图片尺寸、违规项、耗时、状态
  manifest.csv    # id,输出路径,状态,违规数
```

`report.json` 结构固定，方便现场对比：

```
{ "batch": "demo1", "total": 6, "ok": 5, "violations": 1,
  "items": [ { "id": "item_001", "status": "ok", "chars": {"title": 8},
               "image": {"w": 1200, "h": 1200}, "issues": [], "ms": 420 } ] }
```

---

## 8. 验收动作（改一条规则重跑）

1. `python -m app.cli build ... --out out/demo1`
2. 把 `rules.yaml` 的 `title_chars` 从 `18` 改成 `12`
3. 再跑一次 `--out out/demo2`
4. 看 `out/demo2/report.json`：多条 item 出现 `title_too_long`；对应 PNG 里标题换行或截断
5. 这一步就是「规则驱动、可重跑」的证据，不用解释

`python -m app.cli demo` 会把 1–4 自动跑一遍并打印差异，给对方一条命令看完。

---

## 9. 接模型（可选，默认不联网）

```
set OPENAI_BASE_URL=https://api.xxx.com/v1
set OPENAI_API_KEY=sk-xxx
set MODEL_NAME=gpt-4o-mini

python -m app.cli build ... --provider api
```

- `--provider local`（默认）：只从 `assets/images` 取图，不联网
- `--provider mock`：生成纯色占位图，用于测试
- `--provider api`：按 `image_prompt` 调图/文模型，失败自动回退 local 并在报告里记 `fallback`

---

## 10. 部署

```
uvicorn app.api:app --port 8000
POST /build   { items, template, rules }  ->  { batch_id, report }
GET  /out/{batch}/{file}                  ->  静态文件
```

```
docker build -t cardpipe .
docker run --rm -v %cd%/out:/app/out cardpipe
```

---

## 11. 已知边界（明确不做的）

- 不做图库版权接入、不做自动发布到平台
- 不做杂志级复杂版式，只做模板槽位级
- 不做模型微调、不做 UI 编辑器
- 不做多语言排版（中文优先，英文可读即可）

> 写清边界是加分项：优先复用已有资产，先做出可运行、可维护的版本，而不是一步做成平台。

---

## 12. 交付自检表（交前逐条打勾）

- [ ] 无网络、无 key，`local` 模式跑通全流程
- [ ] 中文正常显示（字体文件已加载，缺字体时**报错退出**而不是画方块）
- [ ] 换一个模板 JSON（改坐标/字号）不改代码能出图
- [ ] 缺字段、超字数、图片过小都会进 `report.json`
- [ ] 改 `title_chars` 重跑，报告与成品同步变化
- [ ] PNG 与 PDF 都有，PDF 页面尺寸与画布一致
- [ ] `pytest` 全绿；`app.cli demo` 输出 PASS
- [ ] README 里的命令可以逐条复制执行

