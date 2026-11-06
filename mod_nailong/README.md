# 钢奶龙心 / Hearts of Nailong

把《钢铁雄心 IV》的人物本体替换为圆滚滚的黄色奶龙，保留每个人原有的服装、发型、胡须、配饰、姿态与取景。

当前公开版本 **1.0**，适配 HOI4 **1.19.x**。GitHub与原创意工坊已于北京时间2026-11-07更新，均包含 **5579 个贴图绑定**，比上一安装包增加262个。1.19.3库存的5481张人物素材均已完成，[最后12张接收记录](data/high12-owner-intake-20261105.json)保存来源、原始 PNG、请求与审图资格核对。发布前重新清点本机已安装的1.19.4.1游戏，发现此前库存之外的3个人物来源；当前为 **5481/5484** 人物素材通过，另有4个非人物例外保留原图。此清点不证明这3个来源何时加入游戏。完整正式构建仍有748条既有未解析引用待处理。

[Steam 创意工坊订阅](https://steamcommunity.com/sharedfiles/filedetails/?id=3830400579) · [GitHub 1.0 安装包](https://github.com/XenoAmess/xenoamess_hoi4_dev/releases/tag/nailong-v1.0-20261105)

法国、英国、美国已进行实际界面抽查，法国推进到 1936 年 1 月 4 日。实测版本为 1.19.3.0，范围、截图和机器证据见[实机验收记录](docs/native-resolution-live-qa-2026-10-30.md)。这不代表所有人物、国家、事件和 DLC 组合均已逐项实机遍历。

![法国陆军顾问](assets/screenshots/20261030/france-army-advisors.png)

![开局选国的七张奶龙人物卡](assets/screenshots/20261030/country-selection.png)

游戏贴图逐项采用其原版来源的分辨率。完整高清生成 PNG 原件按原始字节保存在 [`assets/generated_fullsize/`](assets/generated_fullsize/)，用于素材追溯；其中也包含历史版本和未通过审图的结果，不能把素材归档数量当作当前合格数量。[高清索引](data/fullsize-files.json)记录 SHA、尺寸和来源关联。

请将游戏与现实区分开来，尊重不同国籍、族群与背景的玩家，反对歧视，珍惜和平。完整中英双语介绍见 [Workshop 文案](docs/workshop-description.bbcode)。

从 GitHub Release 下载 `gangnailongxin.zip`，解压到 HOI4 用户目录的 `mod` 下，并创建外层 `.mod` 文件指向该目录；也可在创意工坊订阅。与替换相同头像的其他模组可能冲突，建议先单独启用。

开发工具、完整提示词与审图记录保存在仓库中；只有构建器生成的 staging 内容进入游戏包。内部 manifest 如实保存当前覆盖和验收状态。

生产、重试、纯 OCR/键鼠与素材归档规则见 [AGENTS.md](AGENTS.md)。

2026-11-05更新的[离线构建已完成逐文件与母版派生像素验证](data/publication/1.0-update-20261105/build.json)。2026-11-07已完成两平台发布、GitHub完整资产下载核SHA及Steam真实订阅缓存贴图核对。本地发布副本已在1.19.4.1.99a5实机抽查七国选国卡、英国政治界面和新增Alan Brooke/John Vereker顾问小卡；新下载订阅版的启动验证仍待完成。Steam提示必须先退出所有运行游戏才能离线，当前保留《文明VI》，等待用户处理。实际证据、descriptor差异和待办见[发布回执](data/publication/1.0-update-20261105/published-20261107.json)。
