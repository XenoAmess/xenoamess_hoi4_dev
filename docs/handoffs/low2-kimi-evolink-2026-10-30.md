# Kimi LOW2 EvoLink 素材交接（2026-10-30）

## 范围与权限

本次只处理用户在固定提交 `398db2a4959364c4303f9d912397b58df5fe907a` 的 `docs/handoffs/2026-10-30-low-two-pending.md` 中指定的 **2 个 LOW 来源、2 个游戏资源实例**。用户明确要求 Kimi 也使用 evolink.ai 生成这两项。

EvoLink 权限只授予 Kimi 的这次限定任务。**没有改变 Codex 的 EvoLink 权限，也没有修改许可文档。** 不处理其他 LOW，不恢复已暂停的旧 HIGH131 目标。完整原 prompt、原图→用户奶龙参考图的顺序与字节保持不变；内置工具各一次拒绝的历史及冷却重试计数 **0/0** 保留，外部生成不冒充内置重试成功。

## 实际生成与审图

- 模型：`gpt-image-2.5-flare`；3:4、2K、high、opaque，每源一次 `external-01`。
- 两次实际 EvoLink 调用均完成，退出码均为 0，无未知调用。
- Kimi 实际查看了两张 156×210 原图、完整未改原始 RGB 返回图、用户奶龙参考，以及完整白底／青底／Alpha 对照页。
- 两源均为全不透明原图，返回为 1776×2368 RGB，无 Alpha 通道；未见透底、孔洞或背板丢失，未做 Alpha 修补或程序修图。
- 两项均有当前 SHA 绑定的 `hair-features-v1`、`collar-fit-v1` 和可见 Alpha 人工批准。
- 证据：`mod_nailong/experiments/evolink-low2-20261030/review-01-agent.json`、`review-01-evidence.json`、`review-01.png`。

| 原图 SHA-256 | 游戏资源 | EvoLink task | 原始 PNG SHA-256 | 字节 |
|---|---|---|---|---:|
| `13714c9266d4867e2c831f01322fe8647b46db795f3c5673aeb93cd2be8d36d7` | `gfx/leaders/GER/Portrait_Germany_Generic_land_6.dds` | `task-unified-1793328031-ketatciu` | `372696d19eb56a9a51d77b6a896bfa20977c403c4bc4bb7fb2d18025429be7bd` | 5,218,013 |
| `9e6fa74c90e6a74a306bf02b7c08780ec9318e67ef685c9d46cc0fecc670e805` | `gfx/leaders/GER/Portrait_Germany_Generic_land_9.dds` | `task-unified-1793328074-kuys1qpc` | `f84620b46de7b88a1f6bbc2832f3ec2422c48eb42b0bb225a99f1ff7da977cd2` | 5,517,566 |

原始 PNG 母版保存在普通 Git 文件：

- `mod_nailong/assets/generated_fullsize/372696d19eb56a9a51d77b6a896bfa20977c403c4bc4bb7fb2d18025429be7bd.png`
- `mod_nailong/assets/generated_fullsize/f84620b46de7b88a1f6bbc2832f3ec2422c48eb42b0bb225a99f1ff7da977cd2.png`

不是 LFS 指针，不是只放 Release 的附件，也未缩小或重新编码。实验原始输出位于 `mod_nailong/experiments/evolink-low2-20261030/outputs/`；对应 `.request.json`、`.task.json`、`.result.json`、`.prompt.txt`、`executions/` 和 `logs/` 保留实际调用链。

## 美术检查结论

- LOW 6：右向大檐帽、灰棕鬓发和独立眉毛、微张嘴、无胡须、闭合领口及金色服饰组保留；只有一个嘴，未见长脖子、漂浮衣领或奶白围兜。
- LOW 9：左向软野战帽、三枚小圆帽扣、短鬓发、独立眉毛、无新增胡须、闭合领口及斜背带保留；未改成硬顶大檐帽。
- 细徽章、发丝等以低清原图可见差异为限，不声称辨清不可见细节。

## 接入与后续责任

两项素材已完成生成、逐源审图、原始母版保存和正式隔离接入，原始接入提交为 `c17f5089f15042141c18295d5e6c939eaf997182`。完整母版索引为 **7,422 张**，保留上一轮两张拒收母版并加入本次两张新母版。两张 156×210 派生预览已实际查看且 SHA 核验通过，Alpha 均为全 255；游戏构建仍默认使用高清母版。

在这两个来源的 `mod_nailong/data/generated.json` 行中查找 `production_import.schema = low2-kimi-production-import-v1`，并核对 `request_journal`、`generation_inputs`、`production_import` 和对应 `mod_nailong/data/generation-requests/<source_sha256>.json` 中的 `external-*` 证据。原始接入使用经逐路径核验的暂存区和普通单父提交，没有 merge commit 或公开历史改写。

本文是素材位置交接，不预先宣称 Git 推送、固定提交远端读回、完整测试或预览构建已通过；这些独立结果见 `opencode.md` 和 `runtime/low2-evolink-20261030/` 的实际回执。

Kimi 只负责素材生成、逐图审查与正式素材接入，**不负责 HOI4 实机验收**。后续构建／显示适配及纯 OCR＋键鼠实机验收由 Codex 负责。不能将审图页、开发 preview 或文件检查当作实机通过；本交接不声称整个模组已正式发布或全部 LOW／HIGH 已完成。

## 验证材料定位

两源内置失败原始记录精确摘录在 `mod_nailong/experiments/evolink-low2-20261030/original-failure-evidence.json`，绑定既有 `scope.json` 和 `prepared.json` 的 SHA；它不是新的服务调用，也不重置内置重试计数。隔离工作区缺少本地测试依赖时，可运行 `python -X utf8 mod_nailong/experiments/evolink-low2-20261030/tools/low2_test_support.py --worktree <隔离工作区路径>`。该工具只补齐本地脚本、原图索引、原始 prompt 和测试引用，不调用图片生成，不把依赖或其他 LOW 记录纳入提交。
