# 图像侧验证 · 人物素材替换（CardPipe）

> 目的：在已验证「文本 / 模板 / 批量导出」之外，单独验证图像侧三件事：
> ① 自制或已授权的人物图能直接替换模板素材；② 人像常见问题（分辨率不足、横图塞竖槽）能被规则抓住；③ 素材来源可追溯。

## 1. 结论先行

| 验证点 | 结果 | 证据 |
|---|---|---|
| 换人像素材不改代码 | 通过：新增 1 个模板 JSON + 1 个数据文件即可 | `templates/card_person.json`、`data/items_people.yaml` |
| 批量出图 | 5 条 → 5 张 1080x1440 PNG + 5 页 PDF，退出码 0 | `out/people/` |
| 低分辨率人像 | `person_004`（480x640）被规则拦下：`image_too_small` | `out/people/report.json` |
| 横版合影进竖槽 | `person_005`（1600x900）被规则标记：`image_ratio_off` | 同上 |
| 画面裁切 | 竖图进竖槽头部完整；横图进竖槽只保留中间一人 | `out/people/person_001.png` vs `person_005.png` |
| 来源可追溯 | 5 张图全部在 `SOURCES.md` 登记；`selfcheck` 校验通过 | `assets/images/people/SOURCES.md` |
| 授权闸门 | 目录里出现未登记图片时 `selfcheck` 判 FAIL | `tests/test_image_swap.py::test_provenance_check_rejects_unregistered_file` |
| 真实照片机械差异 | 通过：EXIF 方向、3024x4032 大图、4032x3024 横图用合成 JPEG 覆盖 | `tests/test_photo_inputs.py` |

## 2. 素材：自制人物插画（虚构人物）

- 生成脚本：`scripts/make_people.py`（纯本地 PIL 绘制，无网络、无外部素材、无随机数）
- 5 张图：`p01.png` `p02.png` `p03.png`（900x1200 竖版）、`p04.png`（480x640，**故意低分辨率**）、`group.png`（1600x900，**横版合影**）
- 人物与姓名均为虚构，不对应任何真实个人；不做换脸、不拼接他人肖像
- 逐张来源登记在 `assets/images/people/SOURCES.md`

> 换成真实照片时：必须有书面授权，并在 `SOURCES.md` 登记授权方/范围/期限；建议 3:4 竖版、短边 ≥800px。

## 3. 模板：`templates/card_person.json`

画布 1080x1440（#F7F5F2），5 个槽位，仍然只有 text / image 两种类型，渲染器零改动：

| 槽位 | 类型 | 位置/尺寸 | 参数 |
|---|---|---|---|
| `portrait` | image | 72,120 / 560x740（3:4） | `cover`，`radius: 28` |
| `title` | text | 672,120 / 336x150 | 56px，最多 2 行（姓名） |
| `subtitle` | text | 672,286 / 336x60 | 28px（岗位） |
| `body` | text | 672,368 / 336x430 | 26px / 行高 1.55，最多 10 行（简介） |
| `bullets` | text | 72,930 / 936x280 | 30px，前缀「· 」（标签） |

## 4. 数据：`data/items_people.yaml`

| id | 姓名 | 岗位 | 图片 | 尺寸 | 预期 |
|---|---|---|---|---|---|
| person_001 | 林晚晴 | 社区巡检负责人 | p01.png | 900x1200 | 通过 |
| person_002 | 陈北 | 持证飞手 | p02.png | 900x1200 | 通过 |
| person_003 | 周砚 | 图像标注主管 | p03.png | 900x1200 | 通过 |
| person_004 | 苏禾 | 夜班值守调度 | p04.png | 480x640 | `image_too_small` |
| person_005 | 城东巡检小组 | 团队合影 | group.png | 1600x900 | `image_ratio_off` |

## 5. 过程与命令

### 5.1 生成素材（可复跑）

```bash
python scripts/make_people.py
```

```
p01.png: 900x1200
p02.png: 900x1200
p03.png: 900x1200
p04.png: 480x640
group.png: 1600x900
```

### 5.2 人物卡批量出图

```bash
python -m app.cli build --items data/items_people.yaml --template templates/card_person.json --rules rules.yaml --out out/people
```

```
处理条数: 5
失败条数: 0
违规条数: 2
输出目录: ...\DEMO\out\people
耗时: 1.292s（首跑 2.7s 左右，随机器负载波动）
[OK] PNG 5 张，PDF 1 份，report.json / manifest.csv 已写入
```

### 5.3 对照实验：同一批人像塞进原来的产品模板

```bash
python -m app.cli build --items data/items_people.yaml --template templates/card_a.json --rules rules.yaml --out out/people_into_card_a
```

```
处理条数: 5
失败条数: 0
违规条数: 5
```

5 条全部报 `image_ratio_off`：产品模板图片槽是 920x720（1.28:1 横版），人像是 3:4 竖版（0.75），差 0.53 > 容差 0.15。这正是「换素材要连带换模板」的证据，规则先把问题指出来了。

对照批次同样生成了联系表，能直接看到人像被放大裁切、工牌与肩线被切掉：

![人像塞进产品模板](out/people_into_card_a/contact_sheet.png)

### 5.4 生成联系表（便于转发）

```bash
python scripts/contact_sheet.py out/people --out out/people/contact_sheet.png
python scripts/contact_sheet.py out/people_into_card_a --out out/people_into_card_a/contact_sheet.png
```

```
out\people\contact_sheet.png: 5 张，188754 bytes
```

## 6. 导出结果

`out/people/`：

| 文件 | 说明 |
|---|---|
| `person_001.png` ~ `person_005.png` | 5 张 1080x1440 成品 |
| `batch.pdf` | 5 页，页面尺寸 = 画布（540x720pt @144dpi） |
| `report.json` | total=5 / ok=3 / violations=2 |
| `manifest.csv` | 每条成品与 issue 数 |
| `contact_sheet.png` | 5 张缩略图联系表 |

![人物卡联系表](out/people/contact_sheet.png)

单张示例（person_001，竖图进竖槽，头部完整、圆角生效）：

![person_001](out/people/person_001.png)

问题示例（person_005，横版合影塞进竖槽，只保留中间一人，报告给出 image_ratio_off）：

![person_005](out/people/person_005.png)

## 7. 读图结论（图像侧到底验证了什么）

1. **cover 裁切按槽位比例执行**：同一个人像，进 3:4 竖槽头部完整；进 1.28:1 横槽只保留中间区域。裁切不是“缩放铺满”，而是短边对齐后居中裁剪。
2. **圆角遮罩生效**：四角透明像素来自 `radius: 28` 的 mask，不是图片自带圆角。
3. **分辨率下限有用**：480x640 放大到 560x740 后画面发虚，规则在出图前就给出 `image_too_small`，避免整批交付才发现。
4. **比例容差有用**：横图进竖槽的差异被量化成 `image_ratio_off`（0.53 > 0.15），报告里能直接定位到人。
5. **授权可追溯**：素材登记是硬检查，未登记文件会让 `selfcheck` FAIL，避免“来源不明的人像”混进交付。

## 8. 换成真实授权照片的操作步骤

1. 准备 3:4 竖版照片，短边 ≥800px（推荐 900x1200 / 1200x1600）。
2. 放入 `assets/images/people/`（可保留 p01-p04，也可全部替换）。
3. 在 `SOURCES.md` 表格新增一行：文件、尺寸、来源（拍摄/授权方）、授权范围与期限。
4. 修改 `data/items_people.yaml` 里对应条目的 `image` 与文案。
5. 复跑：`python -m app.cli build ...` 与 `python -m app.cli selfcheck`。
6. 若照片主体偏上/偏下，调整模板 `portrait` 的 `y/h` 或改用 `contain`（留白而不是裁切）。

## 9. 边界（明确不做）

- 插画不是照片，不能替代对真实人像画质（逆光、肤色、噪点）的评估；真实照片需按第 8 节另跑一轮。
- 照片的机械差异（EXIF 方向、JPEG 解码、3024x4032 大图缩放、横图比例）已用合成 JPEG 覆盖（`tests/test_photo_inputs.py`），不需要真人图也能验证。
- 不做人脸识别、美颜、抠图、换脸；只做等比缩放、居中裁剪、圆角。
- “授权”由 `SOURCES.md` 登记 + `selfcheck` 校验来兜底，不是法律审查。

## 10. 复跑清单

```bash
python scripts/make_people.py
python -m app.cli build --items data/items_people.yaml --template templates/card_person.json --rules rules.yaml --out out/people
python -m app.cli build --items data/items_people.yaml --template templates/card_a.json --rules rules.yaml --out out/people_into_card_a
python scripts/contact_sheet.py out/people --out out/people/contact_sheet.png
python scripts/contact_sheet.py out/people_into_card_a --out out/people_into_card_a/contact_sheet.png
python -m app.cli selfcheck
pytest -q
```




