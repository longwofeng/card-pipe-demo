# 验收记录 · 图文自动化 Demo（CardPipe）

- 被测对象：本目录（HARNESS_PROMPT.md 要求从零实现的批量图文生产管线）
- 验收时间：2026-10-31
- 执行环境：Windows 11 本机；Python 3.12.0；独立 venv（`.venv`；另有全新 `.venv_dod` 用于安装验收，验收后已删除）
- 依赖：pillow / PyYAML / pydantic / fastapi / uvicorn / pytest（见 `requirements.txt`）
- 字体：`assets/fonts/NotoSansSC-Regular.ttf`（Noto Sans SC Regular，随仓库携带；许可说明见 `assets/fonts/NOTICE.txt`）
- 以下命令均在 `DEMO/` 目录执行，`python` 指 venv 内的解释器；中文输出已按 UTF-8 采集

## 1. DoD 总表（HARNESS_PROMPT.md §11）

| # | 完成定义 | 结果 | 证据 |
|---|---|---|---|
| 1 | `pip install -r requirements.txt` 在干净 venv 里成功 | 通过 | §2.1，全新 `.venv_dod` 安装成功 |
| 2 | `build` 退出码 0，产出 PNG + PDF + report.json + manifest.csv | 通过 | §2.2，6 张 PNG + `batch.pdf` + 2 份清单 |
| 3 | `demo --out out/acceptance` 输出 PASS | 通过 | §2.3，5 项 PASS 全部满足 |
| 4 | `selfcheck` 全项 OK | 通过 | §2.4，7/7 项 OK |
| 5 | `pytest -q` 全绿 | 通过 | §2.5，26 passed |
| 6 | 断网状态下 `local` 模式可跑通 | 通过 | §2.6，死代理下仍 exit 0（local 全程无网络调用） |
| 7 | 删除字体后退出码 3 且提示明确 | 通过 | §2.7，exit 3 + 中文提示，字体已还原 |
| 8 | README 命令逐条可执行 | 通过（Docker 两条除外，见 §6） | §2.1–§2.4、§3 |

## 2. 逐条命令与输出

### 2.1 干净 venv 安装

```bash
python -m venv .venv_dod
.venv_dod\Scripts\python.exe -m pip install -r requirements.txt
```

输出摘要：

```
Successfully installed PyYAML annotated-doc annotated-types anyio click colorama fastapi h11 idna
iniconfig opentelemetry-api packaging pillow pluggy pydantic pydantic-core pygments pytest starlette
typing-extensions typing-inspection uvicorn
install exit=0
```

在同一个干净 venv 内复跑了 `selfcheck`（7/7 OK）、`build`（exit 0）、`pytest`（26 passed）；两套 venv 结果一致，正文引用的是 `.venv` 的最终一次输出。

### 2.2 build（README §2 的命令）

```bash
python -m app.cli build --items data/items.yaml --template templates/card_a.json --rules rules.yaml --out out/demo1
```

输出：

```
处理条数: 6
失败条数: 0
违规条数: 2
输出目录: ...\DEMO\out\demo1
耗时: 1.994s
[OK] PNG 6 张，PDF 1 份，report.json / manifest.csv 已写入
```

退出码 `0`。`out/demo1/` 内容：

| 文件 | 说明 |
|---|---|
| `item_001.png` ~ `item_006.png` | 1080x1440 成品图（dpi=144） |
| `batch.pdf` | 6 页，每页 MediaBox `[0 0 540.0 720.0]`，即 1080x1440 @144dpi |
| `report.json` | total=6 / ok=4 / violations=2，逐条含字数、图片尺寸、issues、ms |
| `manifest.csv` | `id,output,status,issues` 共 6 行数据 |

样例批次刻意放进两条“不合规但可出图”的素材，用来证明校验真的在跑：

- `item_004`：600x600 小图 → `image_too_small` + `image_ratio_off`（status `ok_with_issues`）
- `item_005`：1600x900 横图 → `image_ratio_off`（status `ok_with_issues`）
- `item_006`：`image` 为空 → 走 LocalProvider 占位图，正常产出

### 2.3 demo（改一条规则重跑 → diff → PASS）

```bash
python -m app.cli demo --out out/acceptance
```

输出（完整）：

```
[demo] 第一遍：...\DEMO\rules.yaml（title_chars=18）
[demo] 第二遍：临时副本（title_chars=12，未改动仓库 rules.yaml）
[demo] 第一遍: total=6 ok=4 violations=2 — PNG + PDF 已产出
[demo] 第二遍: total=6 ok=2 violations=4 — PNG + PDF 已产出

[demo] 两次报告差异：
| 范围 | id | 字段 | 第一遍 | 第二遍 |
|---|---|---|---|---|
| batch | - | ok | 4 | 2 |
| batch | - | violations | 2 | 4 |
| item | item_002 | status | ok | ok_with_issues |
| item | item_002 | issues | - | title_too_long |
| item | item_003 | status | ok | ok_with_issues |
| item | item_003 | issues | - | title_too_long |

| issue code | 第一遍 | 第二遍 |
|---|---|---|
| `image_ratio_off` | 2 | 2 |
| `image_too_small` | 1 | 1 |
| `title_too_long` | 0 | 2 |

  [PASS] 第一遍 title_too_long = 0（要求 0）
  [PASS] 第二遍 title_too_long = 2（要求 >= 1）
  [PASS] 第一遍产出 PNG 与 batch.pdf
  [PASS] 第二遍产出 PNG 与 batch.pdf
  [PASS] 两次报告存在差异

PASS
```

退出码 `0`。规则改动只作用于临时目录里的副本，仓库 `rules.yaml` 的 SHA256 前后一致（`tests/test_demo.py` 对此有断言）。

产物：`out/acceptance/run1/`、`out/acceptance/run2/`、`out/acceptance/report_diff.json`、`out/acceptance/report_diff.md`。

> 说明：默认 `on_violation: report` 的语义是“照常出图、问题进报告”，所以两遍 PNG 按设计是同一张，变化体现在报告；要看到成品变化需切到 `truncate`，见 §4.2。

### 2.4 selfcheck

```bash
python -m app.cli selfcheck
```

输出：

```
自检清单：
  [OK] Python 3.12.0 —— 需要 3.11+
  [OK] 字体文件 assets\fonts\NotoSansSC-Regular.ttf —— 缺少中文字体时会直接退出（退出码 3）
  [OK] 中文字形可渲染（Noto Sans SC Regular） —— 抽样非背景像素 11.9%，阈值 5%
  [OK] 样例数据 data\items.yaml —— 6 条，id 唯一
  [OK] 模板 templates\card_a.json —— 1080x1440，文字槽位 3，图片槽位 1
  [OK] 规则 rules.yaml —— on_violation=report，png_dpi=144，pdf=True
  [OK] 输出目录可写 out/ —— 创建与删除探针文件成功

自检通过：7 项全部 OK
```

### 2.5 pytest

```bash
pytest -q
```

```
..........................                                               [100%]
26 passed in 22.32s
```

耗时随机器负载波动，上表为本次验收实测值。覆盖：规则边界（18/19 字、比例恰好等于容差/超容差）、三种 on_violation、中文非空白、画布尺寸、PDF 页尺寸、mock provider、缺字体退出码、demo PASS + diff、两次构建报告逐字段一致（除 ms）。

### 2.6 断网 / local 模式

本机 HTTPS 出网被拦截（`https://pypi.org` TLS 握手失败），local 模式本身也不发起任何网络请求。为了给出可复现的证据，把 HTTP(S) 代理指向死端口后再跑：

```powershell
$env:HTTP_PROXY="http://127.0.0.1:1"; $env:HTTPS_PROXY="http://127.0.0.1:1"
python -m app.cli build --items data/items.yaml --template templates/card_a.json --rules rules.yaml --out out/offline_check
```

```
处理条数: 6
失败条数: 0
违规条数: 2
输出目录: ...\DEMO\out\offline_check
耗时: 3.087s
[OK] PNG 6 张，PDF 1 份，report.json / manifest.csv 已写入
```

退出码 `0`。

### 2.7 删除字体文件

把 `assets/fonts/NotoSansSC-Regular.ttf` 移走后再跑 build：

```
[FONT] 中文字体缺失：...\DEMO\assets\fonts\NotoSansSC-Regular.ttf
请把 NotoSansSC-Regular.ttf 放到 assets/fonts/ 下（或用 CARDPIPE_FONT 指定路径）。没有中文字体时会画出方块，因此这里直接退出。
提示：字体是硬依赖，缺失即退出码 3，不会画出方块。
exit=3
```

退出码 `3`；测试结束后字体已还原，SHA256 与删除前一致。

### 2.8 退出码矩阵（HARNESS §4）

| 场景 | 命令 | 退出码 | 验证位置 |
|---|---|---|---|
| 正常构建 | `build ...` | 0 | §2.2 |
| `on_violation=fail` 且有违规 | `build ...`（rules 副本改 fail） | 2 | `tests/test_cli.py::test_fail_mode_exits_2_without_products` |
| 字体缺失 | `build ...`（字体移走） | 3 | §2.7 |
| 输入格式错误 | `build --items <缺 id 的 yaml>` | 4 | `tests/test_cli.py::test_bad_items_exits_4` |
| demo 通过 | `demo --out ...` | 0 | §2.3 |

## 3. 产物与“截图”路径

| 证据 | 路径 | 看点 |
|---|---|---|
| 正常成品 | `out/demo1/item_001.png` | 中文标题/副标题/圆角图/要点排版正常 |
| 小图仍出图 | `out/demo1/item_004.png` | 600x600 图被 cover 放大，报告同时给出两条 issue |
| 无图占位 | `out/demo1/item_006.png` | `image` 为空时 LocalProvider 生成占位图 |
| 整批 PDF | `out/demo1/batch.pdf` | 6 页，页面尺寸 = 画布 |
| 报告 | `out/demo1/report.json` | 结构固定：batch/total/ok/violations/items |
| 清单 | `out/demo1/manifest.csv` | 每行一条成品与 issue 数 |
| 规则 diff | `out/acceptance/report_diff.md` | `title_too_long` 0 → 2 |
| truncate 成品 | `out/truncate_demo/item_002.png` | 标题末尾出现 `…` |

## 4. 补充验证（DoD 之外，用于说明能力边界）

### 4.1 FastAPI 入口

```bash
uvicorn app.api:app --port 8765
```

实测（本机 PowerShell 调用）：

```
POST /build  {"items":"data/items.yaml","template":"templates/card_a.json","rules":"rules.yaml"}
→ batch=api_702a4bb3cb8b  total=6 ok=4 violations=2
→ files=batch.pdf,item_001.png,...,report.json
GET /out/api_702a4bb3cb8b/report.json  → 200
GET /out/api_702a4bb3cb8b/../../rules.yaml → 404（路径穿越被拦截）
```

batch_id 由 items/template/rules 的内容哈希决定，同内容重复提交落在同一目录。

### 4.2 规则真的能改成品（truncate 模式）

默认 `report` 模式只改报告、不改图。要看到“规则改动直接体现在成品上”，把规则副本改成 `on_violation: truncate` + `title_chars: 12` 再跑：

```bash
python -m app.cli build --items data/items.yaml --template templates/card_a.json --rules out/rules_truncate.yaml --out out/truncate_demo
```

结果：`item_002`/`item_003` 的 title 从 13 字截断为 `城市低空巡查无人机焕新…`（`chars.title=12`，status `truncated`，issue `truncated`），对应 PNG 与 `out/demo1` 的字节内容不同（已比对 SHA256）。

截图：`out/truncate_demo/item_002.png`、`out/truncate_demo/title_crop.png`（标题区放大）。

### 4.3 确定性

`tests/test_determinism.py` 两次独立构建到不同目录（batch 同名），`report.json` 去掉 `ms` 后逐字段相等，issue 顺序也一致。PNG 本身同样可复现（同输入两次构建字节一致）。

## 5. 文件清单

```
app/__init__.py  models.py  materials.py  render.py  rules.py  report.py  cli.py  api.py
templates/card_a.json
data/items.yaml
rules.yaml
assets/fonts/NotoSansSC-Regular.ttf  assets/fonts/NOTICE.txt
assets/images/hero_01.png hero_02.png hero_03.png wide.png small.png
scripts/make_assets.py
tests/conftest.py test_rules.py test_render.py test_cli.py test_demo.py test_determinism.py
Dockerfile  .dockerignore  requirements.txt  pytest.ini  .gitignore
README.md  ACCEPTANCE.md
```

## 6. 未执行项与边界（如实说明）

1. **Docker 构建未执行**：本机有 `docker` CLI（29.8.2），但没有 Docker Desktop/daemon（`C:\Program Files\Docker\Docker\Docker Desktop.exe` 不存在，`docker info` 报 `npipe:////./pipe/dockerDesktopLinuxEngine` 找不到）。因此 `docker build -t cardpipe .` 与 `docker run ...` 未在本机跑过。Dockerfile 按 HARNESS §9 写：`python:3.11-slim` + 随镜像 COPY 字体 + `ENTRYPOINT ["python","-m","app.cli"]`，`CMD` 默认执行 `demo`。
2. **Python 3.11 未实机运行**：本机只有 3.12.0（满足 3.11+）。代码未使用 3.12 专有语法（已扫描 f-string 引号复用等），Docker 基础镜像固定 `3.11-slim`。
3. **字体许可**：字体为系统内 Noto Sans SC 变量字体在 `wght=400` 的静态实例，版权与 OFL 1.1 声明取自字体 name 表，见 `assets/fonts/NOTICE.txt`；对外分发时请随包附上 OFL 全文。
4. `assets/images` 下 5 张图为本地脚本 `scripts/make_assets.py` 生成的抽象素材，未使用任何网络图片。

## 7. 结论

HARNESS_PROMPT.md §11 的 8 条 DoD 中 7 条完全通过；第 8 条（README 命令）除 Docker 构建/运行（本机无 daemon，见 §6）外，其余命令全部实跑通过。`python -m app.cli demo --out out/acceptance` 输出 **PASS**。




