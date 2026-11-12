# 钢奶龙心 1.0 宣传片制作

[导演稿](director-script.zh-CN.md)为本片第一稿：75 秒、16:9、简体中文字幕与普通话旁白，创意为「世界局势很严肃，参谋部很可爱」。本目录保存创作输入，录屏和构建过程材料放在仓库已忽略的 `runtime/` 中。

- `director-script.zh-CN.md`：分镜、旁白、声音、拍摄顺序、简介与宣传口径。
- `shot-plan.json`：镜号、连续时间与旁白窗口；供后续 HOI4 制作集成消费。它是项目自有 sidecar，不是 XAR 的 capture receipt，也不是已拍素材清单。
- `promo-project.json`：XAR 原生创作配置，章节状态全部为 `planned`；每章对应一镜。
- `authoring-receipt-20261112.json`：工具链来源、字节绑定、实际创作阶段验证及本机素材留存位置。

## 工具链与当前阶段

按用户给定的 `../workspace`，从 `C:\workspace\xenoamess_hoi4_dev` 解析出的下载位置为 `C:\workspace\workspace\xar_promo_toolchain`。此次从指定 GitHub 仓库 shallow clone，固定提交为 `6cba48556843bbeabc8f0cfa08ce783255afe0cc`，源码声明与隔离安装的 CLI 均为 **0.3.0**。原有兄弟目录 `C:\workspace\xar_promo_toolchain` 未修改。

隔离 CLI 位于 `runtime/promo-20261112/venv/Scripts/xar-promo.exe`。已执行该 checkout 要求的 Suno skill 字节校验；本次未生成音乐或调用音乐服务。

本次使用 `init` 建立初始脚手架，使用 `start-run` 将最终配置保存为独立快照，使用 `preserve` 绑定导演稿与分镜字节，并执行完整 `authoring` 校验。另以 `xar_promo.storyboard.plan_storyboard` 生成 75 秒草拟时间线。它验证分镜时序，不测量尚不存在的配音时长。

配置中的 `hoi4-ocr-capture` 和 `gangnailongxin-75s` 为拟接入的组件 ID。**当前尚无注册的 HOI4 adapter、preset 或 composer**，因此未运行管线 `plan`、`build` 或媒体 `audit`；本次没有录屏、配音、成片、媒体审查、人工 signoff 或视频上传。创作配置通过与可生成成片分别记录。

## 继续拍摄时

1. 核对当前订阅构建、游戏版本、Steam 离线状态与桌面使用时段；按项目存储策略完成录屏峰值、配额、系统与其他任务预留的准入。当天可用空间快照不能替代录屏空间预留。
2. 按导演稿集中采集选国页与英国界面，生成带源媒体 SHA、PTS、镜头 marks、clean spans 和证据引用的 capture receipt。产品语义保存于 HOI4 sidecar；不借用 CK3 capture 规则。
3. 实现并注册本项目 adapter、preset 与 `PipelineComposer`，使用工具链已有留存、时间线及音轨 API。改动配置后新建 run，保持旧快照及失败材料。
4. 先运行只读 `plan`，再 `build`。用实际配音探测时长替换草拟估计，保留旁白停顿与片尾读字时间。对实际成片做媒体、字节与画面语义核对。
5. 生成精确绑定成片字节的 probe 与待人工审查包。完整观看后，依据具名审阅者明确决定记录 signoff，再离线 export。视频发布另按用户对投放平台的指示执行。

导演稿引用的既有画面来源为 [2026-11-07 实际订阅版抽查](../../data/publication/1.0-update-20261105/subscription-live-qa-20261107.json)，版本数量来自 [发布完成记录](../../data/publication/1.0-update-20261105/completed-20261107.json)。这些历史参考不计作本片新录屏。
