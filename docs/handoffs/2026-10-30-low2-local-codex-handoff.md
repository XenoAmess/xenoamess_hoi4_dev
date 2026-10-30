# LOW2 原图路径与 Codex 接入交接（本地）

## 当前边界

- 用户最新要求：Kimi 后续不再推送，由 Codex 同事接手接入处理。
- 本文只在本地 `docs/handoffs/` 新建交接材料；**不新增 Git commit、不推送、不改生产 manifest 或游戏 payload**。
- 范围仅为两个指定 LOW 来源，不处理其他 LOW 或 HIGH。Codex 的 EvoLink 权限和许可文档均未改变。
- 历史状态须保留：在本交接之前，两图已完成生成、逐图审查和既有接入，已有提交 `0aa28fb3dd37c1c6211530889b7d42f34c73867f` 在远端。此次交接不撤销该历史，也不新增推送。接手时先检查现状，避免重复生成或重复导入。

工作区根目录：`C:/workspace/xenoamess_hoi4_dev`。以下路径均相对于该目录。

## 两张原始 PNG

### 1. LOW 6

- 原图 SHA-256：`13714c9266d4867e2c831f01322fe8647b46db795f3c5673aeb93cd2be8d36d7`
- 游戏资源：`gfx/leaders/GER/Portrait_Germany_Generic_land_6.dds`
- EvoLink 原始返回：`mod_nailong/experiments/evolink-low2-20261030/outputs/13714c9266d4867e2c831f01322fe8647b46db795f3c5673aeb93cd2be8d36d7-01.png`
- 高清母版：`mod_nailong/assets/generated_fullsize/372696d19eb56a9a51d77b6a896bfa20977c403c4bc4bb7fb2d18025429be7bd.png`
- 输出 SHA-256：`372696d19eb56a9a51d77b6a896bfa20977c403c4bc4bb7fb2d18025429be7bd`
- 大小：5,218,013 字节，1776×2368，RGB。
- EvoLink task：`task-unified-1793328031-ketatciu`

### 2. LOW 9

- 原图 SHA-256：`9e6fa74c90e6a74a306bf02b7c08780ec9318e67ef685c9d46cc0fecc670e805`
- 游戏资源：`gfx/leaders/GER/Portrait_Germany_Generic_land_9.dds`
- EvoLink 原始返回：`mod_nailong/experiments/evolink-low2-20261030/outputs/9e6fa74c90e6a74a306bf02b7c08780ec9318e67ef685c9d46cc0fecc670e805-01.png`
- 高清母版：`mod_nailong/assets/generated_fullsize/f84620b46de7b88a1f6bbc2832f3ec2422c48eb42b0bb225a99f1ff7da977cd2.png`
- 输出 SHA-256：`f84620b46de7b88a1f6bbc2832f3ec2422c48eb42b0bb225a99f1ff7da977cd2`
- 大小：5,517,566 字节，1776×2368，RGB。
- EvoLink task：`task-unified-1793328074-kuys1qpc`

这些是没有缩小或重新编码的原始图片，不是审图缩略图、占位图或程序合成图。两张均已实际审阅原图、完整返回图、奶龙参考和白底／青底／Alpha 对照，具备 `hair-features-v1`、`collar-fit-v1` 和可见 Alpha 批准。

## 请求与审图证据

- 审图决定：`mod_nailong/experiments/evolink-low2-20261030/review-01-agent.json`
- 审图对照页：`mod_nailong/experiments/evolink-low2-20261030/review-01.png`
- 对照技术证据：`mod_nailong/experiments/evolink-low2-20261030/review-01-evidence.json`
- 固定范围与请求：`mod_nailong/experiments/evolink-low2-20261030/scope.json`、`prepared.json`
- 内置失败原始记录摘录：`mod_nailong/experiments/evolink-low2-20261030/original-failure-evidence.json`
- 每个 `<source_sha256>-01` 的完整 prompt、request、task、result 位于 `mod_nailong/experiments/evolink-low2-20261030/outputs/`。
- 对应执行回执位于 `mod_nailong/experiments/evolink-low2-20261030/executions/`。

## Codex 接手事项

1. 先核对两个来源在 `mod_nailong/data/generated.json` 中的现有记录。若已有 `production_import.schema = low2-kimi-production-import-v1`，对应素材已经接入，不要重复导入；核对 `request_journal`、`generation_inputs` 和对应 `mod_nailong/data/generation-requests/<source_sha256>.json` 的外部任务证据。
2. 如需使用原始图片，优先读取上面的高清母版；`assets/portraits/` 的 156×210 图片只是派生预览，不应替代高清母版。
3. 后续接入核对、构建／显示适配及纯 OCR＋键鼠实机验收由 Codex 负责。Kimi 本次不再执行这些操作，也不进行新的图片生成或推送。
4. 本交接只说明素材位置和历史状态，不表示 HOI4 实机验收、整个 LOW/HIGH 范围或整个模组发布已经完成。

此前详细材料交接见 `docs/handoffs/low2-kimi-evolink-2026-10-30.md`。实时执行边界追加记录见 `opencode.md`。

## 后续交接发布（2026-10-30）

用户随后要求：“继续。你昨天怎么推送上去的？今天一定也可以。”据此，本次仅将这份交接文档提交并以普通快进方式推送，供 Codex 读取。没有新增图片生成、生产 manifest 修改或 HOI4 实机验收。此前的“不推送”为当时边界，当前按用户最新要求继续。
