# 头像生成、局部修缮与 Alpha 验收方法论

## 目的与证据范围

本文用于后续继续制作“保留原人物服装、构图和可见附属特征的奶龙头像”。核心不是让模型随意画得像，而是把**视觉生成、参数对照、局部修复、人工审图和生产入库**分开处理，避免反复改 prompt 却忽略真正的失败原因。

本机实证来自 `machine_id: bf-202609141645-5434332d4d`，2026-10-24 UTC 的两张 HIGH 原图及其多轮实验：

- Nano Banana 与两轮 GPT Image 2.5 对照：`experiments/evolink-high31-gemini-20261025/`、`experiments/evolink-high31-gpt25-20261025/`。
- Flare 的五轮生成和两轮 Alpha 修复：`experiments/evolink-high31-gpt25-flare-20261025/`。
- 同请求 Sunburst 外缘对照：`experiments/evolink-high31-gpt25-sunburst-alpha-20261025/`。
- 最终人工验收：`experiments/evolink-high31-gpt25-flare-20261025/review-07-alpha-repaired-bilinear.json`。
- 可复用 Alpha 工具：`tools/repair_outer_alpha.py` 与 `tests/test_repair_outer_alpha.py`。

这些是这两张图在当前服务、输入和提示词下的结果，不保证其他模型版本或其他原图必然相同。模型参数以 [EvoLink 官方文档](https://docs.evolink.ai/) 为准；默认生产渠道仍遵守项目当时的用户选择，外部 EvoLink 只在用户明确授权时使用。

## 一、先固定不可妥协的图像合同

开始生成前，先实际查看原图和 `assets/reference/naiwa.png`，逐项写下必须保留的内容，不能只看文件名或历史人物姓名推测外观：

1. **身份**：紧凑圆头、短而宽的颈部过渡、黄色奶龙本体、黑色眼睛配绿色环、小水平嘴，不恢复人鼻、人耳或真人皮肤。
2. **附属特征**：原图实际可见的发型、发色、发际线、眉毛、上唇胡须、鬓角和其他毛发；只有原图确实没有时才省略。
3. **服装与饰物**：帽子、军服类型、领章、勋章、眼镜和其他配饰的形状、数量与位置，尤其不能复制出额外领章或肩章。
4. **构图**：头朝向、视线、表情、姿态、取景、明暗和原摄影背板。
5. **领口**：圆头靠近宽肩，领围随体型调整，保持原领型、开合和前后遮挡；不能夹住粗脖子、形成长柱颈或奶白围嘴。
6. **Alpha**：透明只用于真实外缘，原图内部背板、头发、帽子和衣服不能变成孔洞、烟雾或半透明布料。

`hair-features-v1` 与 `collar-fit-v1` 仍是正式资格条件；模型返回一张图不等于满足合同。

## 二、prompt 的角色分工与写法

### 2.1 每张输入都要有明确角色

多图输入必须说明每张图的用途，避免模型把原人物、旧成品和奶龙参考混用：

- 原图：构图、服装、外貌特征、背板和外缘 Alpha 的唯一来源。
- 奶龙参考：角色身份、眼睛、黄色本体和头颈比例。
- 旧成品（局部修缮时）：需要保留的当前 RGB 内容，不是重新构图的参考。
- 蒙版（若采用局部编辑）：只决定哪些区域允许改变，不把蒙版当作新画面。

### 2.2 可复用 prompt 骨架

按源图改写方括号内容，不要把所有规则堆成互相冲突的长文：

```text
Image 1 is the composition target. Image 2 is the identity reference.
Replace only the person with the yellow 奶龙: compact round head, short wide neck,
solid black eyes with green rings and no white sclera, small horizontal mouth,
no human nose or realistic human eyes.

NON-NEGOTIABLE SOURCE FEATURES:
[实际发型/发色/眉毛/胡须/鬓角；没有的项目不要添加]
Preserve the exact head orientation and gaze, cap, uniform, decorations,
their original positions and counts, and a naturally fitted collar.

BACKGROUND IS LOCKED:
Keep the original [浅色/深色] photographic backplate, brightness, texture and opacity.
Do not replace it, darken it or cut it out.
```

末尾只复核最关键的两三项，例如“浅色背板、棕发、黑眼、无新增眼白”，不要反复堆砌同义否定词。

### 2.3 常见失误与对应提示

- 掉胡子、掉鬓角：逐项写明颜色、位置和大致形状，不能只说“保留毛发”。
- 棕发变金发：明确 `BROWN ... never turn it blond`。
- 新增眼白：明确 `solid black eyes with green rings and no white sclera`。
- 领章复制：明确 `original positions and counts; never duplicate collar or shoulder ornaments`。
- 正面化：明确保留原头朝向和视线，禁止把侧向源图改成正面。
- 背板变暗：优先写“背景颜色、亮度、纹理和不透明度锁定”，不要同时反复要求整图透明化。

## 三、对照实验：每轮只改变一个变量

保留独立实验目录、逐次 prompt、去密 request、task ID、原始 PNG、失败回执和审图结果。新 attempt 使用新文件名，不覆盖旧结果。

有效的比较方式：

| 变量 | 固定内容 | 能回答的问题 |
| --- | --- | --- |
| 只改 prompt | 模型、输入、尺寸、质量、background | 哪类特征能通过文字恢复？ |
| 只改 model | prompt、输入和其他参数 | 是模型差异还是 prompt 缺陷？ |
| 只改 background | prompt、模型和输入 | 背板丢失是否由透明路线驱动？ |
| 只改编辑底图 | 模型、prompt 和参数 | 局部修缮是否比整图重绘更稳定？ |

没有新证据时，不要机械重复“再优化一次 prompt”。若同类失败连续出现，应切换到参数、输入底图、蒙版或确定性后处理，而不是无限堆词。

### 模型与 background 的实际边界

- `gpt-image-2.5-flare` 在本组实验中较快恢复了人物特征，但不是每次都能保持背板或发色。
- `gpt-image-2.5-sunburst` 官方定位偏编辑精度，但**不是专用抠图保证**；同 prompt、同输入下，它仍产生了整圈外缘淡出。
- `background=opaque` 能避免透明抠图倾向，但会直接返回 RGB，prompt 无法在这种模式下可靠“补出 Alpha”。
- `background=transparent` 能产生 RGBA，但不保证 Alpha 的位置、形状或数值与原图一致。RGBA 本身也可能是错误的全框光晕或烟雾背板。
- `mask_url` 是后续可试的局部编辑路线：只开放真实外缘，锁死内部。它仍属生成结果，必须重新审图，不能预设逐像素一致。
- 2026-10-25 的 HIGH131 实测进一步限定第五条通用路线：对真实透明外缘的素材，若先让模型生成中性工作底色，而新人物/相框轮廓又小于来源 Alpha 轮廓，机械覆盖来源 Alpha 会把工作底色留成明显外圈；`rgb_unchanged` 与 Alpha 数值匹配不能使这种派生图合格。此类来源可直接用 `background=transparent` 和对应的透明外缘 prompt 生成原生 RGBA，经完整原图、母版及白底/青底/Alpha 实际审查后接受其原生 Alpha，不再自动替换来源 Alpha。只有轮廓、背板与工作底色相容时才继续做 Alpha-only 修复；全幅不透明房间/背板仍可保留 RGB 并恢复其原 Alpha。

### HIGH131 便笺的高清局部返修（待首轮实图验证）

2026-10-25 本机逐图审查发现，部分 65×67 小卡片的便笺具有**上排两组、下排两组不规则灰记**。多轮整图重绘将它们替换成重复圆点、短划或长横条；即使反复强化文字约束，仍会丢失分组、相对长度和紧凑占位。这些可见差异不能用“原图文字不可辨”豁免，也不能把简单圆点数量等同于原图的不规则分组。

为此准备 `raw-hd-edit-v1`：以当前被驳回的高清返回图为 Image1，以原图为 Image2，以用户奶龙参考为 Image3。每个请求必须绑定当前驳回图的 SHA、对应审图、三个输入的顺序和字节，以及固定 Git 提交中全部原始 PNG 已读回核验的证明。它不是继续叠加旧 prompt，也不是用程序修图冒充重新生成；未被驳回的正确人物、衣服、领口和背板应尽量保留。

该路线在首轮实际返回前只是待验证方案，不宣称已经解决便笺问题。仍须保存完整实际 prompt、任务与输出 SHA，逐张查看原图、完整母版和白底/青底/Alpha 对照。真实透明外缘的卡片须检查原生透明、摄影背板和小右侧标签，不能因文件是 RGBA 就自动通过。不能处理或重发无任务号且远端结果未知的调用。

## 四、本组失败分流得到的关键结论

1. 通用“变成奶龙”容易丢人物特征，源图逐项约束通常比换模型更先有效。
2. 反复强化浅色背板仍出现烟雾时，继续堆背景词未必有用；应验证 `background` 参数是否主导结果。
3. `opaque` 在本组第四轮给出了最佳 RGB：浅色背板、灰鬓/小胡子、棕发和纯色黑眼都恢复，但缺少外缘 Alpha。
4. 再改回 `transparent` 后，模型可以返回 RGBA，却新增整圈圆角光晕；换 Sunburst 也没有修复该特定问题。
5. 最终有效方案是：**先取得最佳 RGB，再仅恢复 Alpha**。这不允许修改 RGB，因此不会破坏已经合格的服饰、毛发和背板。

应把“RGB 美术不合格”“没有 Alpha 通道”“有 Alpha 但外缘错误”视为三种不同问题，不能混为一谈。

## 五、可复用的 Alpha-only 修复

### 5.1 使用条件

仅在以下条件同时满足时使用：

- 已有一张 RGB 美术基本合格的母版；
- 原图及原 Alpha 可读取，且能证明其外缘要求；
- 用户明确授权确定性后处理；
- 保存父图 SHA、原图 SHA、输出 SHA、方法和审图，不把后处理冒充模型原生输出。

若用户要求必须纯生成，先尝试 `mask_url` 局部编辑，不用本方法冒充生成结果。

### 5.2 为什么用 BILINEAR，而不是 LANCZOS

本组实测：

- LANCZOS 会改变 Alpha 极值和角点，例如底部 `36` 被压成 `0`，`225` 被压成 `218`。
- 标准 BILINEAR 在本组尺寸映射中同时保留源极值和四角值，并维持平滑过渡。
- 角点相同不能代替全图 Alpha 检查；仍须核对整张 Alpha 与白底/青底合成。

工具：`mod_nailong/tools/repair_outer_alpha.py`。它只替换 Alpha，保留 RGB 原字节，拒绝覆盖已有输出。

```text
cmd.exe /c python mod_nailong/tools/repair_outer_alpha.py --source runtime/references/<SOURCE_SHA>.png --base mod_nailong/assets/generated_fullsize/<BASE_MASTER_SHA>.png --output mod_nailong/experiments/<EXPERIMENT>/outputs/<SOURCE>-alpha-repaired.png
```

返回 JSON 必须逐项核对：

- `method=source-alpha-resize-bilinear-rgb-unchanged-v1`；
- `rgb_unchanged=true`；
- `alpha_matches_resized_source=true`；
- 输出为 RGBA，尺寸与父图一致；
- `source_corner_alpha_tl_tr_bl_br`、`resized_corner_alpha_tl_tr_bl_br` 与 `output_corner_alpha_tl_tr_bl_br` 一致；
- 记录 `resized_alpha_sha256` 和输出 PNG SHA。

不要用本工具修改衣领、毛发或其他 RGB 美术缺陷；那些问题仍需重新生成或另行授权的编辑。

## 六、人工验收清单

必须实际查看原图、完整母版和白底/青底/Alpha 对照页，不能只看程序统计或缩略黑底预览。

### 人物与服装

- 奶龙本体、黑眼绿环、小嘴和短宽颈是否正确，有无恢复人鼻或真人眼睛；
- 发型、发色、眉毛、胡须、鬓角是否与原图可见特征一致；
- 头朝向、视线、表情、帽子、衣服、饰物数量及位置是否一致；
- 领口是否自然贴合，有无夹脖、长柱颈、漂浮领子或重复领章。

### 背板与 Alpha

- 原摄影背板是否仍在，亮度、颜色和纹理是否被替换；
- 白底和青底是否出现内部孔洞、烟雾、布料透光、整圈光晕或新增相框；
- RGB 是否表示完全无 Alpha，RGBA 是否仍可能是错误 Alpha；
- Alpha 极值和四角值只是证据的一部分，不能代替整图目视判断；内部 `252–254` 也不应单独成为拒绝理由。

早期 Lanczos 对照只作历史证据，最终采用 BILINEAR 版本。任何被替换或被弃用的输出都保留原始 PNG，不覆盖、不重新编码。

## 七、正式导入与可追溯性

1. 用 `portraits.py import` 导入最终 PNG，并通过 `--method` 写明真实生成与修复方法，不能仍写成内置 imagegen。
2. 原版尺寸预览与高清母版分开；builder 默认读取 `assets/generated_fullsize/<输出SHA>.png`，高清母版直接进普通 Git，不放 Release 附件。
3. 追加新的 generation attempt，绑定父图、原图 Alpha、最终输出、review 和授权；旧失败 attempt 不改写，累计服务重试次数不清零。
4. 队列先进入 `generated_pending_visual_review`，实际人工审图后再批准；外部修复应标为 `approved_external_alpha_repair`，不能伪造成内置冷却重试成功。
5. 用 `master_archive.py sync-git` 和 `audit-git` 核对所有当前、历史及实验母版，再用 `verify-tree` 验证真实 Git blob；推送后还要匿名读回固定 commit 的 PNG 字节。
6. 只提交本任务文件，保留其他来源、旧回执和未决状态，不为提高完成数而误批。

常用验证命令：

```text
python -m unittest discover -s tests -p test_evolink_skill_client.py
python -m unittest discover -s tests -p test_repair_outer_alpha.py
python mod_nailong/tools/portraits.py coverage --public
python mod_nailong/tools/master_archive.py sync-git
python mod_nailong/tools/master_archive.py audit-git
python mod_nailong/tools/master_archive.py verify-tree --commit <COMMIT>
python mod_nailong/tools/build_release.py --preview --check --source-key <SOURCE_SHA>
```

`coverage`、双构建、DDS 解码和远端 SHA 只证明各自层面；HOI4 实际显示仍须按项目规则用新鲜离线证据、原始截图、OCR 与真实键鼠另行验收。

## 八、下次执行的最短路线

1. 看原图，列出发型、毛发、服装、构图、背板和 Alpha 合同。
2. 固定原图与奶龙参考，先写源图专属 prompt。
3. 每轮只改一个变量，保留所有成功、失败和弃用记录。
4. 若人物特征不对，先修 prompt；若背板持续丢失，检查 `background`，不要无限堆词。
5. 取得最佳 RGB 后，分别验收人物、背板和外缘；不要把 RGB 合格误当 Alpha 合格。
6. 需要纯生成时试 `mask_url` 局部编辑；用户授权确定性修复时，直接用 BILINEAR Alpha-only 路线。
7. 实测 RGB 未变、Alpha 映射、角点、白底/青底和领口，再批准。
8. 追加真实生产记录，保留旧次数和旧图，完成 Git blob、远端字节及选定子集构建验证；实机另行验收。
