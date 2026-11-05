# HIGH12：Kimi EvoLink 原始素材与接入交接（2026-11-05）

## 结论与边界

- 指定的12个 HIGH 不同原始 SHA 均已生成、逐图实际审查并正式接入；本范围 **12/12**。
- 当前人物来源清单为 **5481/5481（100%）**；4个非人物例外继续保留。该数字不代表 HOI4 实机验收或公开发布已经完成。
- 使用 EvoLink `gpt-image-2.5-flare`，`1:1`、`2K`、`high`、`transparent`、每次 `n=1`。共有17次新任务：12个首次任务和5次美术返修任务；其中两个任务在轮询断连后按原 task ID 恢复，没有重新 POST。
- 12张当前合格图及5张历史拒收图均为未经重新编码的2048×2048原始 PNG，已放入普通 Git 母版库。没有程序修图、通用头像替代或 LOW 操作。
- 原内置请求、拒绝回执和已消耗次数不重写。`8e9f9483…` 的旧内置失败仍保留，另以 `resolved_by_external_task` 绑定本次独立外部成功素材；不称为内置冷却重试成功。
- 第12张的初次服装拒收经放大复审撤回，旧决定和复审决定都保留；未派发那次不必要的返修。详见实验目录的 `precall-cancellations.json` 和 `review-source12-attempt01-agent-recheck.json`。

## 12个正式素材

以下路径均相对仓库根目录。每张的完整实际 prompt、有序输入、去密 request、task/result 和审图均在 `mod_nailong/experiments/high12-evolink-20261105/`。

### 1. `gfx/interface/ideas/idea_GER_adolf_hitler.dds`

- 原始 DDS SHA-256：`33e6a3dfa8f8a3fea4594dfaa04a4a226241dd9955270508df7a2352ef3ef62a`
- 原始 PNG：[mod_nailong/experiments/high12-evolink-20261105/outputs/33e6a3dfa8f8a3fea4594dfaa04a4a226241dd9955270508df7a2352ef3ef62a-02.png](<../../mod_nailong/experiments/high12-evolink-20261105/outputs/33e6a3dfa8f8a3fea4594dfaa04a4a226241dd9955270508df7a2352ef3ef62a-02.png>)
- 高清母版：[mod_nailong/assets/generated_fullsize/189070c774b26b579f404506972da47d06de2d353d581148ac9293fab07f52c0.png](<../../mod_nailong/assets/generated_fullsize/189070c774b26b579f404506972da47d06de2d353d581148ac9293fab07f52c0.png>)
- 原始 PNG SHA-256：`189070c774b26b579f404506972da47d06de2d353d581148ac9293fab07f52c0`；6286402字节，2048×2048，RGBA。
- EvoLink task：`task-unified-1793819425-6i7br6bi`；使用 attempt `external-02`。
- 原尺寸预览：`mod_nailong/assets/portraits/33e6a3dfa8f8a3fea4594dfaa04a4a226241dd9955270508df7a2352ef3ef62a.png`（65×67，仅为派生素材，不替代母版）。

### 2. `gfx/interface/ideas/idea_GER_hans-karl_freiherr_von_esebeck.dds`

- 原始 DDS SHA-256：`38ae905d145650f7a2e84edbb492c6b0dda5b95bf9e5b15e086e3c660c13b5ef`
- 原始 PNG：[mod_nailong/experiments/high12-evolink-20261105/outputs/38ae905d145650f7a2e84edbb492c6b0dda5b95bf9e5b15e086e3c660c13b5ef-01.png](<../../mod_nailong/experiments/high12-evolink-20261105/outputs/38ae905d145650f7a2e84edbb492c6b0dda5b95bf9e5b15e086e3c660c13b5ef-01.png>)
- 高清母版：[mod_nailong/assets/generated_fullsize/a7c5b149d793a53de38c2f3cefa7cd871dc0826bd636b44833c5be1ddec3ab1e.png](<../../mod_nailong/assets/generated_fullsize/a7c5b149d793a53de38c2f3cefa7cd871dc0826bd636b44833c5be1ddec3ab1e.png>)
- 原始 PNG SHA-256：`a7c5b149d793a53de38c2f3cefa7cd871dc0826bd636b44833c5be1ddec3ab1e`；6021979字节，2048×2048，RGBA。
- EvoLink task：`task-unified-1793818359-mjaaxi64`；使用 attempt `external-01`。
- 原尺寸预览：`mod_nailong/assets/portraits/38ae905d145650f7a2e84edbb492c6b0dda5b95bf9e5b15e086e3c660c13b5ef.png`（65×67，仅为派生素材，不替代母版）。

### 3. `gfx/interface/ideas/idea_GER_kurt_student.dds`

- 原始 DDS SHA-256：`8e9f94831dea633dc354f1a0c8e1f5a8e05dfafde745936b4bad707a9aaf3b2b`
- 原始 PNG：[mod_nailong/experiments/high12-evolink-20261105/outputs/8e9f94831dea633dc354f1a0c8e1f5a8e05dfafde745936b4bad707a9aaf3b2b-01.png](<../../mod_nailong/experiments/high12-evolink-20261105/outputs/8e9f94831dea633dc354f1a0c8e1f5a8e05dfafde745936b4bad707a9aaf3b2b-01.png>)
- 高清母版：[mod_nailong/assets/generated_fullsize/fc951ccf61a797a6c3166b8a6c689055dfbfc37b41063114f36732bf915013b2.png](<../../mod_nailong/assets/generated_fullsize/fc951ccf61a797a6c3166b8a6c689055dfbfc37b41063114f36732bf915013b2.png>)
- 原始 PNG SHA-256：`fc951ccf61a797a6c3166b8a6c689055dfbfc37b41063114f36732bf915013b2`；6165415字节，2048×2048，RGBA。
- EvoLink task：`task-unified-1793818500-sbjt14pa`；使用 attempt `external-01`。
- 原尺寸预览：`mod_nailong/assets/portraits/8e9f94831dea633dc354f1a0c8e1f5a8e05dfafde745936b4bad707a9aaf3b2b.png`（65×67，仅为派生素材，不替代母版）。

### 4. `gfx/interface/ideas/idea_GER_albert_kesselring.dds`

- 原始 DDS SHA-256：`9464705420ed2f798008c9f9e8bcd9a8754b01e377387205d80bc5dc00ae75a8`
- 原始 PNG：[mod_nailong/experiments/high12-evolink-20261105/outputs/9464705420ed2f798008c9f9e8bcd9a8754b01e377387205d80bc5dc00ae75a8-01.png](<../../mod_nailong/experiments/high12-evolink-20261105/outputs/9464705420ed2f798008c9f9e8bcd9a8754b01e377387205d80bc5dc00ae75a8-01.png>)
- 高清母版：[mod_nailong/assets/generated_fullsize/bb397898e730be14d8381aa58e6e86481dc582ee51c34654ba6cf3fd5a40fa17.png](<../../mod_nailong/assets/generated_fullsize/bb397898e730be14d8381aa58e6e86481dc582ee51c34654ba6cf3fd5a40fa17.png>)
- 原始 PNG SHA-256：`bb397898e730be14d8381aa58e6e86481dc582ee51c34654ba6cf3fd5a40fa17`；5915789字节，2048×2048，RGBA。
- EvoLink task：`task-unified-1793818834-et7xxph1`；使用 attempt `external-01`。
- 原尺寸预览：`mod_nailong/assets/portraits/9464705420ed2f798008c9f9e8bcd9a8754b01e377387205d80bc5dc00ae75a8.png`（65×67，仅为派生素材，不替代母版）。

### 5. `gfx/interface/ideas/idea_GER_erhard_milch.dds`

- 原始 DDS SHA-256：`a62531815cbf7f3313009170e2fd07c1bf0964c0de7345e23d7f1de7b7f6f549`
- 原始 PNG：[mod_nailong/experiments/high12-evolink-20261105/outputs/a62531815cbf7f3313009170e2fd07c1bf0964c0de7345e23d7f1de7b7f6f549-01.png](<../../mod_nailong/experiments/high12-evolink-20261105/outputs/a62531815cbf7f3313009170e2fd07c1bf0964c0de7345e23d7f1de7b7f6f549-01.png>)
- 高清母版：[mod_nailong/assets/generated_fullsize/8634cb45f611da8201f2db1d5da9d5b6814f35865de961b1da78a9997a225902.png](<../../mod_nailong/assets/generated_fullsize/8634cb45f611da8201f2db1d5da9d5b6814f35865de961b1da78a9997a225902.png>)
- 原始 PNG SHA-256：`8634cb45f611da8201f2db1d5da9d5b6814f35865de961b1da78a9997a225902`；6300737字节，2048×2048，RGBA。
- EvoLink task：`task-unified-1793818967-4buajw8f`；使用 attempt `external-01`。
- 原尺寸预览：`mod_nailong/assets/portraits/a62531815cbf7f3313009170e2fd07c1bf0964c0de7345e23d7f1de7b7f6f549.png`（65×67，仅为派生素材，不替代母版）。

### 6. `gfx/interface/ideas/idea_aleksandr_vasilevsky.dds`

- 原始 DDS SHA-256：`b01d01b6e13c9514db3bd1a209fc9b1f24be78c505090b92f474b9ba57924dae`
- 原始 PNG：[mod_nailong/experiments/high12-evolink-20261105/outputs/b01d01b6e13c9514db3bd1a209fc9b1f24be78c505090b92f474b9ba57924dae-01.png](<../../mod_nailong/experiments/high12-evolink-20261105/outputs/b01d01b6e13c9514db3bd1a209fc9b1f24be78c505090b92f474b9ba57924dae-01.png>)
- 高清母版：[mod_nailong/assets/generated_fullsize/8a781c1c79a97c0caa54e3e9d471364606784f82e7fad2e99532d2b846f3b4d4.png](<../../mod_nailong/assets/generated_fullsize/8a781c1c79a97c0caa54e3e9d471364606784f82e7fad2e99532d2b846f3b4d4.png>)
- 原始 PNG SHA-256：`8a781c1c79a97c0caa54e3e9d471364606784f82e7fad2e99532d2b846f3b4d4`；5536859字节，2048×2048，RGBA。
- EvoLink task：`task-unified-1793819204-gfic4410`；使用 attempt `external-01`。
- 原尺寸预览：`mod_nailong/assets/portraits/b01d01b6e13c9514db3bd1a209fc9b1f24be78c505090b92f474b9ba57924dae.png`（65×67，仅为派生素材，不替代母版）。

### 7. `gfx/interface/ideas/idea_GER_adolf_hitler.dds`

- 原始 DDS SHA-256：`c15aafc0dc3060ff939740ec2c391e7a14980498386a17cf0993504a915b67ec`
- 原始 PNG：[mod_nailong/experiments/high12-evolink-20261105/outputs/c15aafc0dc3060ff939740ec2c391e7a14980498386a17cf0993504a915b67ec-03.png](<../../mod_nailong/experiments/high12-evolink-20261105/outputs/c15aafc0dc3060ff939740ec2c391e7a14980498386a17cf0993504a915b67ec-03.png>)
- 高清母版：[mod_nailong/assets/generated_fullsize/e100ff15acfd0ccdac557dcc71bccc68224cf5f109a4183c130d1e9270f007b5.png](<../../mod_nailong/assets/generated_fullsize/e100ff15acfd0ccdac557dcc71bccc68224cf5f109a4183c130d1e9270f007b5.png>)
- 原始 PNG SHA-256：`e100ff15acfd0ccdac557dcc71bccc68224cf5f109a4183c130d1e9270f007b5`；5748784字节，2048×2048，RGBA。
- EvoLink task：`task-unified-1793820770-if2l46qb`；使用 attempt `external-03`。
- 原尺寸预览：`mod_nailong/assets/portraits/c15aafc0dc3060ff939740ec2c391e7a14980498386a17cf0993504a915b67ec.png`（65×67，仅为派生素材，不替代母版）。

### 8. `gfx/interface/ideas/idea_GER_gerd_von_rundstedt.dds`

- 原始 DDS SHA-256：`c7ac85859a15f75c3d36b1d6621bd5e2287eeb19cbbfedcadc7d7502a21c175b`
- 原始 PNG：[mod_nailong/experiments/high12-evolink-20261105/outputs/c7ac85859a15f75c3d36b1d6621bd5e2287eeb19cbbfedcadc7d7502a21c175b-01.png](<../../mod_nailong/experiments/high12-evolink-20261105/outputs/c7ac85859a15f75c3d36b1d6621bd5e2287eeb19cbbfedcadc7d7502a21c175b-01.png>)
- 高清母版：[mod_nailong/assets/generated_fullsize/ea15d94b5b2d6d7db4055ec8daab37f390cc0e15a29b2faee3948d8d28534ac2.png](<../../mod_nailong/assets/generated_fullsize/ea15d94b5b2d6d7db4055ec8daab37f390cc0e15a29b2faee3948d8d28534ac2.png>)
- 原始 PNG SHA-256：`ea15d94b5b2d6d7db4055ec8daab37f390cc0e15a29b2faee3948d8d28534ac2`；6384284字节，2048×2048，RGBA。
- EvoLink task：`task-unified-1793819844-bqi98v0c`；使用 attempt `external-01`。
- 原尺寸预览：`mod_nailong/assets/portraits/c7ac85859a15f75c3d36b1d6621bd5e2287eeb19cbbfedcadc7d7502a21c175b.png`（65×67，仅为派生素材，不替代母版）。

### 9. `gfx/interface/ideas/idea_GER_erich_von_manstein.dds`

- 原始 DDS SHA-256：`d3322a668fc15d4e71320f8a566bc8ab4471d4064204d57f4d91dcd1883a45d4`
- 原始 PNG：[mod_nailong/experiments/high12-evolink-20261105/outputs/d3322a668fc15d4e71320f8a566bc8ab4471d4064204d57f4d91dcd1883a45d4-03.png](<../../mod_nailong/experiments/high12-evolink-20261105/outputs/d3322a668fc15d4e71320f8a566bc8ab4471d4064204d57f4d91dcd1883a45d4-03.png>)
- 高清母版：[mod_nailong/assets/generated_fullsize/16903e031dfc9521a6c1ba89f3de61d6ade7562458391d570fd8029d785f45d6.png](<../../mod_nailong/assets/generated_fullsize/16903e031dfc9521a6c1ba89f3de61d6ade7562458391d570fd8029d785f45d6.png>)
- 原始 PNG SHA-256：`16903e031dfc9521a6c1ba89f3de61d6ade7562458391d570fd8029d785f45d6`；6667980字节，2048×2048，RGBA。
- EvoLink task：`task-unified-1793821574-62cx07yr`；使用 attempt `external-03`。
- 原尺寸预览：`mod_nailong/assets/portraits/d3322a668fc15d4e71320f8a566bc8ab4471d4064204d57f4d91dcd1883a45d4.png`（65×67，仅为派生素材，不替代母版）。

### 10. `gfx/interface/ideas/idea_GER_erwin_rommel.dds`

- 原始 DDS SHA-256：`d4eda7fb9c1871cd6b4e7a061d9d582e192cd51fdd9d9b9bec31ce9e8df9650a`
- 原始 PNG：[mod_nailong/experiments/high12-evolink-20261105/outputs/d4eda7fb9c1871cd6b4e7a061d9d582e192cd51fdd9d9b9bec31ce9e8df9650a-01.png](<../../mod_nailong/experiments/high12-evolink-20261105/outputs/d4eda7fb9c1871cd6b4e7a061d9d582e192cd51fdd9d9b9bec31ce9e8df9650a-01.png>)
- 高清母版：[mod_nailong/assets/generated_fullsize/6215db95ed284fe5b32b69036ea247d1aa8d6e3ac6dfe0d782aab6655a5ec1a9.png](<../../mod_nailong/assets/generated_fullsize/6215db95ed284fe5b32b69036ea247d1aa8d6e3ac6dfe0d782aab6655a5ec1a9.png>)
- 原始 PNG SHA-256：`6215db95ed284fe5b32b69036ea247d1aa8d6e3ac6dfe0d782aab6655a5ec1a9`；6265020字节，2048×2048，RGBA。
- EvoLink task：`task-unified-1793820663-cpyj8961`；使用 attempt `external-01`。
- 原尺寸预览：`mod_nailong/assets/portraits/d4eda7fb9c1871cd6b4e7a061d9d582e192cd51fdd9d9b9bec31ce9e8df9650a.png`（65×67，仅为派生素材，不替代母版）。

### 11. `gfx/interface/ideas/idea_GER_heinz_guderian.dds`

- 原始 DDS SHA-256：`defb98346af3176be6cf218258ba4cbf86bea2b5e7f6ee94425f39998b4f6a82`
- 原始 PNG：[mod_nailong/experiments/high12-evolink-20261105/outputs/defb98346af3176be6cf218258ba4cbf86bea2b5e7f6ee94425f39998b4f6a82-01.png](<../../mod_nailong/experiments/high12-evolink-20261105/outputs/defb98346af3176be6cf218258ba4cbf86bea2b5e7f6ee94425f39998b4f6a82-01.png>)
- 高清母版：[mod_nailong/assets/generated_fullsize/e4ee44ea94fde2a2b2e5aa955841c54983260b27df112c353424655fcbdefa49.png](<../../mod_nailong/assets/generated_fullsize/e4ee44ea94fde2a2b2e5aa955841c54983260b27df112c353424655fcbdefa49.png>)
- 原始 PNG SHA-256：`e4ee44ea94fde2a2b2e5aa955841c54983260b27df112c353424655fcbdefa49`；5631214字节，2048×2048，RGBA。
- EvoLink task：`task-unified-1793821082-9qtok1zg`；使用 attempt `external-01`。
- 原尺寸预览：`mod_nailong/assets/portraits/defb98346af3176be6cf218258ba4cbf86bea2b5e7f6ee94425f39998b4f6a82.png`（65×67，仅为派生素材，不替代母版）。

### 12. `gfx/interface/ideas/idea_todt.dds`

- 原始 DDS SHA-256：`fd4fad64842952e3361367704f26250e328946ee19a9c7452d62a385b70189ea`
- 原始 PNG：[mod_nailong/experiments/high12-evolink-20261105/outputs/fd4fad64842952e3361367704f26250e328946ee19a9c7452d62a385b70189ea-01.png](<../../mod_nailong/experiments/high12-evolink-20261105/outputs/fd4fad64842952e3361367704f26250e328946ee19a9c7452d62a385b70189ea-01.png>)
- 高清母版：[mod_nailong/assets/generated_fullsize/bbe32799a646ce600c5c3f63a5bf7f57c92cdc69605d90d6c98fabd7f9515bf5.png](<../../mod_nailong/assets/generated_fullsize/bbe32799a646ce600c5c3f63a5bf7f57c92cdc69605d90d6c98fabd7f9515bf5.png>)
- 原始 PNG SHA-256：`bbe32799a646ce600c5c3f63a5bf7f57c92cdc69605d90d6c98fabd7f9515bf5`；5854115字节，2048×2048，RGBA。
- EvoLink task：`task-unified-1793821312-c36uf07b`；使用 attempt `external-01`。
- 原尺寸预览：`mod_nailong/assets/portraits/fd4fad64842952e3361367704f26250e328946ee19a9c7452d62a385b70189ea.png`（65×67，仅为派生素材，不替代母版）。

## 接入和后续责任

- 12个来源的原尺寸确定性 preview 双构建通过：11项按当前 DLC 覆盖配置，另1个同名原版变体按 base-only 单独验证。完整正式构建仍受既有748条未解析角色引用限制，本次没有消除或隐瞒该边界。
- 17张新增原始 PNG 均完成本地 SHA、PNG 和普通 Git blob 校验；完整原件索引为7742张、16,071,492,721字节。固定提交的远端读回以交付结果为准，不把本地校验冒充远端成功。
- 本次同时修正历史审计对同源已解决重试、已有外部 task 和 Alpha 修复字段的识别，以及未来新请求的相框＋便笺整体透明区文字。既有请求、拒绝、图像及重试次数不回改。
- `mod_nailong/data/generated.json` 的12行均具备当前 SHA 绑定的 `hair-features-v1`、`collar-fit-v1`、可见 Alpha 批准；请求日志位于 `mod_nailong/data/generation-requests/<原始SHA>.json`。
- `outputs-index.json` 索引全部17张原始输出；`approved-masters.json` 只列12张当前合格图。白底／青底／Alpha 对照是审图证据，不是游戏 payload。
- 游戏贴图按各自原始尺寸派生。Codex 后续负责必要构建核对、部署及纯 OCR＋键鼠的 HOI4 离线实机验收；本执行者没有声称完成实机或公开发布。
- 原始小卡的 EvoLink 输入附件与公开读回见 `input-release.json`；返修输入使用 `evolink-high12-repair-input-20261105`，只包含实际拒收图的原始 PNG。
- 实时进度另存于本目录 `live-progress.json`。根目录 `opencode.md` 的既有 OpenCode 导出未被重写，只在独立字段中记录本任务状态；它不是本任务唯一的审计来源。

## 实际交付结果

- 原始素材提交：`1e55909f2bee7293aea7105b101b879e93d0e82c`；已普通快进推送 `master`。
- Python **581/581**、JavaScript **24/24** 通过。完整素材审计通过：5481个正式人物来源、7742张原件、8833条请求记录。
- 固定提交 `1e55909f…` 的远端原始 PNG 读回已覆盖全部7742张：20张实际完整下载并核对 SHA/字节；7722张在 blob、路径和大小一致时复用已有真实读回。不是仅凭 push ACK 或本地缓存宣称完成。
- 补充的全库 `verify-tree` 重复读取曾在1800秒超时，未被冒充为通过；完成依据是全库本地 SHA 审计、新增原件 Git blob 校验及上述远端固定提交证据。
- 本任务素材接入与交付完成；HOI4 实机验收、正式发布资格和后续公开更新仍由 Codex 另行负责。

## Codex 接收

用户要求接收后，已将本交付与上次剩余清单逐项对应：12个来源完全一致，当前5481/5481已知人物素材通过，4个非人物例外保留。核对了12张当前资格、输入/提示词/请求/任务绑定、17张原始 PNG及普通Git blob；保留既有逐图审查，没有重新生成或重新授予美术资格。旧合格素材、原内置请求前缀、失败字段和整个重试队列的字节均未改变。

17张交付原件已从固定素材提交完整下载核对SHA和大小（含5张历史拒收图），详见[独立远端读回](../../mod_nailong/data/fullsize-readbacks/20261105-high12-owner-intake.json)和[接收回执](../../mod_nailong/data/high12-owner-intake-20261105.json)。本次没有重跑同事已完成的全库测试或构建，也没有执行游戏、Steam或公开安装包更新；748条既有未解析引用仍如实保留。
