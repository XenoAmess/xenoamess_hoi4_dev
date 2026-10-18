# 高清母版与游戏用图

用户于 2026-10-18 明确决定：**高清素材直接作为文件放进 Git，不使用 Release 附件。** 每张母版位于 [`assets/generated_fullsize/`](../assets/generated_fullsize/)，文件名为工具返回的原始 PNG 的 SHA-256。使用普通 Git blob，完整保留原始字节、实际分辨率与透明度，不改编码、不放 LFS 指针。

[`data/fullsize-files.json`](../data/fullsize-files.json) 是当前逐图索引，包含路径、原始字节数、尺寸、模式、生成 journal / 实验关联及 prompt SHA。当前版本由 `data/generated.json` 的 `generated_fullsize_image` 定位；旧版本由 `revision_history[].previous_fullsize_image` 和请求 journal 定位。实验、被替换版本及未通过审图的实际输出都保留真实身份，保存到 Git 不代表已通过美术验收。

用户于同日进一步要求游戏默认直接使用高清图，只有实际确定必须缩放、否则会出问题的个别项才允许缩放。此前统一按原版尺寸制作游戏图是保守实现，不是已证实的引擎硬限制；该默认现已取消。builder 直接读取 `generated_fullsize_image`，核对完整 SHA 后在原始分辨率下无损编码 RGBA DDS，不先降采样、不加模糊；缺失或改变的母版直接阻止构建，不退回小图。每个 binding 记录母版 SHA、原版尺寸、实际导出尺寸及 `resized: false`。高清纹理在各游戏界面的显示兼容仍须分别实测，不能以编码/解码成功代替。

`assets/portraits/` 中 156×210、65×67、42×46 等旧原版尺寸图继续作为审图缩略预览、历史派生和既有资格定位，不再是默认游戏 payload 输入。对照页和网页为了屏幕排版显示缩略图，不影响母版或游戏导出。高清例子可直接查看[罗斯福原始 1081×1455 样例](media/fullsize-portrait-example.png)及[来源记录](fullsize-portrait-example.json)。

导出逐图流式写 staging/ZIP，双构建用流式 SHA 比较归档，避免整库高清同时进入内存。常规 checkpoint 使用 `--preview --check --validation-sample 4`，只验收四个明确标注的开发样本；不声称整库构建通过。当前 bounded 导出上限为 256 MiB staging，计及 ZIP 或双构建时仍须执行共享容量策略；完整高清包需要先完成重型写入预算，而不能因机器尚有空间就跳过。少量实机样本可用 `--preview --source-key <原图SHA> --output <新目录>` 独立构建；它不解锁正式 release，也不抵扣全量覆盖。

新准备的局部返修直接使用当前原始高清 PNG 作为编辑目标，避免把 65×67 等游戏缩图再次放大编辑而丢失胡须、领章和勋饰细节。请求记录同时绑定母版 SHA 和派生游戏图 SHA。已声明的母版缺失或字节改变时拒绝准备，先恢复原件；只有历史记录从未声明母版时才允许明确标注的旧缩图迁移。此前已冻结或实际调用的输入、冷却重试原请求均保持原样，不能追认为过去已经使用高清输入。

首张实际高清编辑已返回并通过逐图审查，其 1235×1274 输入、实际调用前校验和输出身份见[验收记录](../data/fullsize-edit-workflow-qualification.json)。这只证明该次输入与结果，不代替后续审图。

后续流程：

1. 内置图片工具调用前冻结完整实际 prompt 和输入；成功返回后，`generation_requests.py finish` 保留高清原件，并建立供对照审查的原版尺寸预览。游戏导出直接使用高清原件，跳过预览。按输出 SHA 命名，修订不能覆盖旧输出。
2. `python mod_nailong/tools/master_archive.py sync-git` 从全部当前、历史及实验记录中收集已知输出，只接受已记录 SHA 完全相同的 PNG，补齐文件和索引。不把原版游戏素材或同目录内的无关生成图纳入。
3. `python mod_nailong/tools/master_archive.py audit-git` 核对全部原件、索引与记录。正常 `git add`、`git commit`、`git push` 提交实际 PNG；不能仅提交清单。
4. `python mod_nailong/tools/master_archive.py verify-tree --commit <commit>` 流式读取真实 Git blob，逐图核对大小和 SHA-256；远端固定 commit 还须完整读取原始 PNG 并保存独立核验回执。本机存在、Git 推送成功和远端字节读回是三个不同事实。

本机采用同卷硬链接把原始 PNG 纳入工作树，避免再复制一套素材；Git 仍保存完整实际文件，不是链接指针。禁止原地编辑这些不可变文件。其他卷或机器不能套用本机硬链接、容量或校验结论。

2026-10-18 迁移初始快照：`machine_id: bf-202609141645-5434332d4d`，观察时间 `2026-10-17T17:36:19.439579+00:00`，425 个当前头像、545 个不同高清输出、共 1,019,175,675 bytes，全部从已记录来源找回，无缺失。清点只证明本机可读；提交和远端核验以 [`data/fullsize-git-checkpoint.json`](../data/fullsize-git-checkpoint.json) 的固定 commit 及实际结果为准。后续新图不自动算进旧快照。

历史说明：此前先只保留本机原件，随后建立了 `art-masters-001` 至 `004` 分卷附件。用户本次决定覆盖该存储方式。旧上传器已经移除，`archive --tag ...` 入口明确拒绝上传；旧附件只在全部 PNG 已进入 Git 且远端字节完整核验后退役。原 [`data/fullsize-archives.json`](../data/fullsize-archives.json)、旧备份快照和 prompt 传输勘误保留历史事实，并注明退役后的可用性；不能继续把已撤下附件当成可下载副本。

本机生成缓存、构建和其他派生副本继续遵守共享存储策略及有期限的用途复核。本次迁移不删除本机原始 PNG、不改写公开 Git 历史、不改变 Steam 状态。

退役已完成：`machine_id: bf-202609141645-5434332d4d`，`2026-10-17T18:07:41.825196+00:00`。在固定 commit `eca824fd909a0555b37627cb917a2facd1b03f0d` 的 545 张原件全部完成匿名下载与 SHA-256/大小核验后，已移除上述四个素材 Release 的 35 个附件。Release 条目仅保留历史说明和 Git 文件链接；精确 asset ID、时间与读回见[退役回执](../data/fullsize-release-retirement.json)。后续新输出继续直接进入 Git。
