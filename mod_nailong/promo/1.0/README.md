# 钢奶龙心 1.0 宣传片制作

[导演稿](director-script.zh-CN.md)为本片第二稿：75 秒、16:9、简体中文字幕与普通话旁白，创意为「世界局势很严肃，参谋部很可爱」。按用户最新偏好，尽量避免中国相关人物成为重点；个人特写、群像主位、备用镜头、封面与片尾优先使用英美法意人物，英国 Baldwin 为主角。本目录保存创作输入，录屏和构建过程材料放在仓库已忽略的 `runtime/` 中。

- `director-script.zh-CN.md`：分镜、旁白、声音、拍摄顺序、简介与宣传口径。
- `shot-plan.json`：镜号、连续时间、旁白窗口及 `casting_policy` 选角偏好；供后续 HOI4 制作集成消费。它是项目自有 sidecar，不是 XAR 的 capture receipt，也不是已拍素材清单。
- `promo-project.json`：XAR 原生创作配置，章节状态全部为 `planned`；每章对应一镜。
- `authoring-receipt-20261112-r2.json`：当前第二稿的字节绑定、验证与独立留存 run。
- `authoring-receipt-20261112.json`：初稿历史回执；其原稿与配置见固定提交 `9440e147dffce2150777df99030c47c7caca7886`，原有 `director-v1` run 保留，不重写为第二稿证据。
- `capture-progress-20261112.json`：首轮实际录屏的范围、字节绑定、工具链留存与尚待补拍项。

## 工具链与当前阶段

按用户给定的 `../workspace`，从 `C:\workspace\xenoamess_hoi4_dev` 解析出的下载位置为 `C:\workspace\workspace\xar_promo_toolchain`。此次从指定 GitHub 仓库 shallow clone，固定提交为 `6cba48556843bbeabc8f0cfa08ce783255afe0cc`，源码声明与隔离安装的 CLI 均为 **0.3.0**。原有兄弟目录 `C:\workspace\xar_promo_toolchain` 未修改。

隔离 CLI 位于 `runtime/promo-20261112/venv/Scripts/xar-promo.exe`。已执行该 checkout 要求的 Suno skill 字节校验；本次未生成音乐或调用音乐服务。

本次使用 `init` 建立初始脚手架，使用 `start-run` 将最终配置保存为独立快照，使用 `preserve` 绑定导演稿与分镜字节，并执行完整 `authoring` 校验。另以 `xar_promo.storyboard.plan_storyboard` 生成 75 秒草拟时间线。它验证分镜时序，不测量尚不存在的配音时长。

第二稿同步修改 S04、S05、S07、S08 的人物安排和 S05 旁白，使用独立 `director-v2` run 绑定新字节，保持原 75 秒节奏。

配置中的 `hoi4-ocr-capture` 和 `gangnailongxin-75s` 为拟接入的组件 ID。**当前尚无注册的 HOI4 adapter、preset 或 composer**，因此未运行管线 `plan`、`build` 或媒体 `audit`。创作阶段的两份历史回执保持当时状态；后续实际拍摄进展另记。

## 首轮拍摄进展

2026-11-12 已实际录下 6 段、合计 95.966 秒原片：七国选国页、法国／意大利／美国／英国人物信息卡，以及英国地图到政治面板的切换。采集使用 FFmpeg 的桌面像素录屏，原生 1024×768、30 fps；源视频无音轨，技术回执记录了实际解码帧数、时间和焦点监测。首轮未采集中国相关人物特写。

选国页与四国信息卡抽帧可用。英国切换镜头有悬浮提示，地图部分可裁切使用，头像揭示需补拍；三张陆军顾问候选卡尚未拍摄。桌面在后续准备时被切到另一任务的《文明 VI》，录屏器拒绝了焦点不符的下一段；当前停止游戏输入，等待用户协调独占桌面时段。此前的英国与顾问历史截图不冒充本轮录像。

本轮 6 份 generic capture receipt 已由 `xar_promo.capture.load_capture_receipt` 验证实际字节；原片、回执、导演稿、分镜、离线中文旁白与中文字幕共 26 个素材已通过 CLI 保存在独立 `capture-001` run。录屏与过程材料位于本机已忽略的 `runtime/promo-capture-20261112/`，尚未作为视频上传到 GitHub 或其他平台。旁白及临时合成配乐只作后续剪辑输入；尚无完整成片、具名人工 signoff 或视频发布。

本次采用单段时长、文件大小及总新增工作包上限的短片段采集；留存时实际工作包约 135 MB，上限为 512 MiB。未执行大规模录屏／构建的空间准入，也未把未知的全项目占用或其他任务预留写成 0；后续如扩大到重型媒体写入，仍须先满足仓库存储策略。

## 继续拍摄时

1. 核对当前订阅构建、游戏版本、Steam 离线状态与桌面使用时段；按项目存储策略完成录屏峰值、配额、系统与其他任务预留的准入。当天可用空间快照不能替代录屏空间预留。
2. 按导演稿集中采集选国页与英国界面，生成带源媒体 SHA、PTS、镜头 marks、clean spans 和证据引用的 capture receipt。产品语义保存于 HOI4 sidecar；不借用 CK3 capture 规则。
3. 实现并注册本项目 adapter、preset 与 `PipelineComposer`，使用工具链已有留存、时间线及音轨 API。改动配置后新建 run，保持旧快照及失败材料。
4. 先运行只读 `plan`，再 `build`。用实际配音探测时长替换草拟估计，保留旁白停顿与片尾读字时间。对实际成片做媒体、字节与画面语义核对。
5. 生成精确绑定成片字节的 probe 与待人工审查包。完整观看后，依据具名审阅者明确决定记录 signoff，再离线 export。视频发布另按用户对投放平台的指示执行。

导演稿引用的既有画面来源为 [2026-11-07 实际订阅版抽查](../../data/publication/1.0-update-20261105/subscription-live-qa-20261107.json)，版本数量来自 [发布完成记录](../../data/publication/1.0-update-20261105/completed-20261107.json)。这些历史参考不计作本片新录屏。
