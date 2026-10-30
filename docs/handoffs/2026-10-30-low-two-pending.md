# 钢奶龙心：最后两张 LOW 头像交接（2026-10-30）

供接手的同事使用。本交接只涉及下面两个**不同原始 SHA-256** 的 LOW 来源；它们在当前 `mod_nailong/data/generated.json` 中都没有合格返图记录。2026-10-30 本机核对时，LOW 为 **701/703**，全头像来源为 **5236/5238**（含 4 个已记录的非人物原版保留例外）。这不是 100% 完成或正式发布验收。

## 两个待完成来源

| 项目 | LOW 6 | LOW 9 |
| --- | --- | --- |
| 原始 DDS SHA-256 | `13714c9266d4867e2c831f01322fe8647b46db795f3c5673aeb93cd2be8d36d7` | `9e6fa74c90e6a74a306bf02b7c08780ec9318e67ef685c9d46cc0fecc670e805` |
| 安装包 | `dlc/dlc036_by_blood_alone` | `dlc/dlc036_by_blood_alone` |
| 游戏资源路径 | `gfx/leaders/GER/Portrait_Germany_Generic_land_6.dds` | `gfx/leaders/GER/Portrait_Germany_Generic_land_9.dds` |
| catalog Asset ID | `63ca34a2c8a3b90bfa75` | `4bd53739fda50ed225be` |
| 原图 | 156×210，RGBA；实际 alpha 极值 255/255 | 156×210，RGBA；实际 alpha 极值 255/255 |
| 调用时第一张输入 PNG SHA-256 | `eb8c39b200f8d51a532be150f3991002d0f5562449d2b580c5d03ea5da1d7c74` | `5d6e668076e4b8a9104757d11d3234cc27862f6a185143e09af8fe74d6d85d83` |
| 实际 prompt SHA-256 | `04071e87bb5034cc365274387a5bfdb1679b89510e6487e1b8ca4960dac582b5` | `3214b028c15952defcce67153a9938aa32aeeb6de281f903002e28f9303e9e33` |
| 首次调用开始 UTC | `2026-10-29T17:11:26.608811+00:00` | `2026-10-29T17:12:06.844142+00:00` |
| 终态收到 UTC | `2026-10-29T17:12:00.486865+00:00` | `2026-10-29T17:12:43.073903+00:00` |
| 请求 ID | `73f0be11-f6a6-4625-bb5d-d6793b6f6ceb` | `68416274-29e8-488d-a105-2ad40381783d` |
| 实际结果 | `moderation_blocked`，`moderation_stage=output`，`output_created=false` | `moderation_blocked`，`moderation_stage=output`，`output_created=false` |
| 当前累计冷却重试 | 0/8；只有首次调用 | 0/8；只有首次调用 |

两次调用的第二张输入均为用户提供的 [奶龙参考图](../../mod_nailong/assets/reference/naiwa.png)，SHA-256 为 `766ae05fcdab3bd41f9f0967e64f387de3adafef0f29626570d5670d9b460976`；`transparent_background=false`。原始人物素材仅在本机游戏安装包和本地转换缓存，不作为完整游戏资产上传。两个来源的本地转换图分别在 `runtime/references/<原始 DDS SHA-256>.png`，跨机器接手时应从对应安装包重取并核对 SHA。

完整实际 prompt 已在调用前冻结，分别见 [LOW 6 prompt](../../mod_nailong/assets/prompts/13714c9266d4867e2c831f01322fe8647b46db795f3c5673aeb93cd2be8d36d7-001.txt) 和 [LOW 9 prompt](../../mod_nailong/assets/prompts/9e6fa74c90e6a74a306bf02b7c08780ec9318e67ef685c9d46cc0fecc670e805-001.txt)。完整调用、输入顺序、错误原文和文件校验值见 [九项调用终态回执](../../mod_nailong/data/extra-retry-rounds/20261030-remaining-low-nine-one-immediate-round-completed.json) 中对应 `results`，以及两份请求日志：[LOW 6](../../mod_nailong/data/generation-requests/13714c9266d4867e2c831f01322fe8647b46db795f3c5673aeb93cd2be8d36d7.json)、[LOW 9](../../mod_nailong/data/generation-requests/9e6fa74c90e6a74a306bf02b7c08780ec9318e67ef685c9d46cc0fecc670e805.json)。本机实际发送前快照位于 `runtime/dispatch-actual/low9-20261030-<原始 DDS SHA-256>-001.json`。

## 用户的最新验收决定与交接动作

用户于 2026-10-30 表示：如果这两张各自曾有“此前认为不通过”的实际返图，可以采用它们。但逐来源日志只有上述一次服务拒绝，均未产生 PNG，当前也没有属于这两个原始 SHA 的旧生成行。因此该决定**不能凭空形成两张图**，也不能把其他原始 SHA 的相似头像当作本项完成。历史上另有被美术拒绝但实际返回 PNG 的来源，其图不属于这两个 SHA。

接手时先按原始 SHA 查找可能尚未汇入的**真实同源返图**。若找到，校验输出原始字节 SHA、输入归属和完整调用记录，实际审图后按用户这次的接受决定登记并导入高清母版；保留旧审图及拒绝历史。若找不到，两项继续是待完成。是否允许再请求须结合 [图片拒绝重试规则](../../mod_nailong/docs/image-retry-policy.md)、[当前重试队列](../../mod_nailong/data/image-retry-queue.json) 与服务实际反馈判断；不能通过改词、改色、换输入或换通道规避这两次服务拒绝。每次实际请求仍须先保存完整 prompt 和实际发送快照，返回后保存结果及 SHA。只有两张各自真实返图并完成审图、入库，LOW 才可从 701/703 变成 703/703。

证据机器：`bf-202609141645-5434332d4d`。本交接是当前状态说明；不改动生成记录、重试次数或历史回执。
