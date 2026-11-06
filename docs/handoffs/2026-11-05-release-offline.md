# 2026-11-05 离线构建与后续发布交接

用户已要求“发布”，随后明确“先完成离线构建，桌面稍后再用”。当前阶段只完成构建和发布材料；共享桌面仍由其他任务使用。桌面可用后继续原发布任务，无需重复询问已给出的发布授权。此文不是上传、实机通过或公开回读回执。

产品保持“钢奶龙心”1.0，更新既有 Workshop 项目 `3830400579`。GitHub 拟创建日期标签 `nailong-v1.0-20261105`，保留已经公开的 `nailong-v1.0` 标签和旧安装资产。实际是否创建、上传和公开，以 [准备状态](../../mod_nailong/data/publication/1.0-update-20261105/prepared.json)及后到发布回执为准。

规范构建位于本机 `dist/release-1.0-update-20261105`，源码冻结为 `f33e5f0220f122c35ff3dc8efffca775a29d8b03`。用 [build.json](../../mod_nailong/data/publication/1.0-update-20261105/build.json)固定 ZIP、manifest、母版派生像素证明的 SHA、机器与时间。源码冻结后的文档提交不改变已验证构建输入。正式 staging 只能由 builder 产生，保持原样；安装包不含高清母版、工具或原版导出。

此包有5579个贴图绑定，较上一版增加262个，旧路径无移除、旧贴图字节无变化。同名路径按已安装DLC优先级实际选用5398个独立人物来源及4个非人物例外；全库存的5481个已审人物来源是另一数量。当前1.19.4.1重新清点发现3个未制作人物来源；748条历史未解析引用保留。内部 `preview=true`、`art_complete=false` 如实保存，公开产品名称与版本遵守用户指定的1.0，不据此冒充全覆盖。

桌面恢复后的工作按以下顺序进行：

1. 获取新鲜原始截图、OCR、桌面尺寸和窗口状态。历史截图中存在《文明VI》和其他活动窗口，不能复用旧焦点或坐标，也不关闭其他游戏。Steam、启动器与HOI4只用 `tools/desktop.py` 的截图/OCR及真实键鼠；按该工具规则核对HWND、内容矩形、语言和截图时效。
2. 先确认Steam离线状态并保存新鲜截图/OCR，再做本包HOI4抽查。部署只复制已验证 staging，沿用独立本地测试外层 `.mod`，不污染规范输出。文件部署不证明游戏已加载；记录真实启用路径、版本、可见头像和抽查范围。至少从 `delta-from-previous.json` 的新增路径选择一个实际可展示位置，不能只凭旧包已有头像证明新增素材显示。若Steam在线，启动任何游戏前先检查其他机器会话，不抢占账号。
3. 抽查后准备独立上传副本及用户目录外层 `.mod`。只在该外层保留既有 `remote_file_id=3830400579`，仓库 descriptor 和规范 staging 不含此字段。旧发布外层文件曾因与订阅项身份重复造成零启用；历史备份在 `runtime/publication-backup/gangnailongxin.mod`。先核对实际来源与payload，避免上传旧文件夹或把本地测试项误当订阅项。
4. 用启动器实际界面更新原Workshop项目，提交完整拟发布说明并保留成功截图。上传后通过公开页面读回标题、介绍和更新说明，保存实际项目ID、时间、机器与出处。拟文案位于 [中英说明](../release-changelogs/nailong/1.0-20261105.md)、[Steam Change Notes](../release-changelogs/nailong/1.0-20261105-steam.txt)和 [Workshop介绍](../../mod_nailong/docs/workshop-description.bbcode)，发布时按实际新包验收范围更新。
5. 让Steam实际下载订阅更新，与本包逐文件核对，单独记录启动器descriptor元数据差异。禁止向Workshop缓存复制本地构建来伪造下载。完成必要上传/下载后立即恢复Steam离线，并用新鲜原图/OCR读回“离线模式”。然后在唯一正确的订阅项启用状态下记录HOI4真实加载。
6. GitHub新日期标签/Release使用同一验证ZIP和manifest，公开标题保持“钢奶龙心 1.0”。实际发布后完整下载公开资产核SHA，记录真实release/asset身份、固定提交和读回结果；上传ACK或API摘要不代替完整字节验证。保留旧公开资产。发布记录和永久changelog只追加已发生事实。
7. 各可审阅单元按项目规则精确提交并正常推送；本项目 `master`、共享模型仓库 `main`，分别保持唯一Git写者。更新本交接的准备状态及README时区分两个平台各自真实状态。

本轮本地文本模型的两项实际请求与人工纠错已归档到[固定共享案例](https://github.com/XenoAmess/local-model-operations/blob/d228b946cfea6997f9c319ab7fd51433dc21c96d/docs/evidence/2026-11-05-hoi4-release-category-arithmetic.json)。模型文本、历史1.19.3抽查及旧订阅包1.19.4.1记录均不替代本包实机验收。

2026-11-07后到状态：用户再次明确要求发布到Steam及GitHub，已恢复桌面步骤。GitHub已公开，实际身份与当时未完成的读回状态见 `github-published-20261107.json`；Steam本次上传仍在进行。启动器spawn报ENOENT后，经真实Explorer地址栏启动同一SHA的hoi4.exe已进入游戏载入画面；载入不等于实机抽查通过。后续使用 `runtime/release-20261107/payload-ready.json` 指定的独立副本，规范构建原件保持完整。

2026-11-07后续已完成：两平台公开、GitHub两客户端完整下载核SHA、Steam原条目成功更新并由客户端下载manifest30649826571776600，5579贴图与缩略图全匹配，descriptor仅客户端序列化/远端ID差异。公开介绍及中英文Change Notes回读完成。本地包已实际抽查七国选国卡、英国政治和新增Alan Brooke/John Vereker小卡。独立发布副本的外层naiwa_world.mod已备份后移出注册目录，避免与实际ugc_3830400579.mod重号；未向Steam缓存复制任何本地素材。

剩余桌面步骤：Steam大屏幕互联网设置明确提示“在进入离线模式前必须退出所有正在运行的游戏。”保留《文明VI》，已向用户询问处理方式，尚未获答；Steam仍在线，新下载订阅版尚未启动。已退出大屏幕模式并保留客户端/游戏，不反复上传。后续先处理该实际阻塞、保存新鲜离线截图，再核对启动器仅真实ugc_3830400579.mod启用并实机。dlc_load已备份后指向真实ugc_3830400579.mod，移除对已退役本地注册的引用；这是可逆文件部署，启动器playset和游戏实际加载尚未验证。最新小型机器回执 `published-20261107.json` 与 `subscription-config-prepared-20261107.json` 保留上述边界；先前记录作为各观察时点快照保留。
