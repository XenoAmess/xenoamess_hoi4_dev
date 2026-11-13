# 钢奶龙心 1.0 宣传片

75秒审片版已完成拍摄、合成、全片解码检查和工具链证据审计，当前等待具名人工完整观看。画面为1920×1080、30fps，含中文合成旁白、烧录字幕和原创临时配乐；本次未上传视频，也未记录人工signoff或执行发布export。

本机视频：`runtime/promo-capture-20261112/film-build-004/gangnailongxin-promo-review-v1.mp4`。字幕：`runtime/promo-capture-20261112/audio/prepared-v1/narration.zh-CN.srt`。完整字节绑定、工具版本、失败尝试和验收范围见[拍摄与成片回执](filming-receipt-20261113.json)。这些媒体及过程文件留在已忽略的runtime中，未作为GitHub附件发布。

[导演稿第二稿](director-script.zh-CN.md)采用「世界局势很严肃，参谋部很可爱」的75秒结构。按用户偏好，人物主位使用英国Baldwin、美国、法国和意大利领袖，以及英国Alan Brooke、Edmund Ironside、John Vereker；未拍摄中国人物特写，标题和片尾以Baldwin为主角。原生1024×768实机画面保持比例，高清角色插入明确标注“角色美术”。

2026-11-12首轮录下6段95.966秒；2026-11-13经用户明确协调桌面后，补拍干净的英国政治界面与三位陆军顾问候选卡，累计8段143.966秒。旧有悬浮提示的政治镜头保留但未用于成片。补拍前后均显示1936年1月1日12:00，本任务未任命顾问或消耗政治点。拍摄后通过菜单退出HOI4，保留《文明 VI》，并用新截图人工读回Steam“离线模式”。

工具链位于用户要求的`../workspace`所解析出的`C:/workspace/workspace/xar_promo_toolchain`，固定提交`6cba48556843bbeabc8f0cfa08ce783255afe0cc`，实际CLI版本0.3.0。原有兄弟checkout未修改。已运行其要求的Suno技能字节检查；旁白使用离线SAPI Huihui，临时配乐由程序合成，未调用音乐或图像生成服务。

隔离CLI为`runtime/promo-20261112/venv/Scripts/xar-promo.exe`；[项目接入包](../integration/README.md)提供adapter、preset和composer。真实制作输入为`production-inputs-v2.json`，本机环境变量`NAILONG_PROMO_INPUTS`指向它。每张美术、每段录屏、配音、配乐和选用时间范围均绑定实际文件字节。

全片经历四个保留的run：首个在片尾淡出参数失败；第二个生成后发现混音真峰值偏高；第三个因owner参数误用了已有workdir，被工具链在渲染前拒绝；第四个全片构建成功。片尾参数改为FFmpeg可接受的`0.5`，两条音轨增益各降低3dB。最终2250帧，容器75.021354秒，48kHz双声道AAC，实测综合响度−22.3LUFS、真峰值−0.6dBFS，完整解码返回0。声音质量仍需人工试听。

原生`film-004`run通过完整authoring验证。媒体审计覆盖精确SHA、字节和16组实际抽帧/OCR的完整性；它不授予美术或人工影片批准。使用公开live probe生成精确字节绑定后，CLI review先只读规划、再生成22帧的待审包，状态保持pending。审片包在`runtime/promo-capture-20261112/pending-review-002/`。原生配置章节仍为创作阶段的planned；实际构建事实由独立run与回执记录。

本轮工作包持续受512MiB上限约束，未删除任何旧素材或修改高清PNG母版。未知的全项目占用、其他任务预留没有记作0；未把此小型有界工作包当成大规模媒体写入准入。

`authoring-receipt-20261112*.json`、`capture-progress-20261112.json`和`integration-receipt-20261112.json`保存各自当时阶段。旧导演稿及五秒组件不倒改成全片证据。`shot-plan.json`保留导演计划，实际旁白时码见制作输入和SRT；时窗微调均在原章节内，75秒总节奏与旁白原词保留。旧发布数量和验收范围仍只引用[2026-11-07订阅版抽查](../../data/publication/1.0-update-20261105/subscription-live-qa-20261107.json)，不冒充本片的新库存普查。
