# HOI4 创意工坊封面

2026-10-31 核对，适用本机 HOI4 1.19.3.0 / Paradox Launcher 2026.13。

模组根目录使用真正的 `thumbnail.png`，与 `descriptor.mod` 同级。仓库内 descriptor 和用户目录外层 `.mod` 都引用 `picture="thumbnail.png"`；发布 staging 不携带 `remote_file_id`，该 ID 仅保留在用户目录外层 `.mod`。

HOI4 社区作者的[上传指南](https://steamcommunity.com/sharedfiles/filedetails/?id=2122282451)说明上述命名、路径和两个 descriptor 的引用方法。指南的具体像素上限是作者的历史经验，不据此宣称游戏存在固定的 499 像素硬限制。官方 HOI4 Wiki 两页在本次访问返回 HTTP 401，未把镜像当成本次直接读到的官方正文。

[Steamworks 主预览图接口说明](https://partner.steamgames.com/doc/api/ISteamUGC#SetItemPreview)本身允许 JPG/PNG/GIF；因此“Steam 平台完全不支持 JPG”是错误结论。[上传结果说明](https://partner.steamgames.com/doc/api/ISteamUGC#SubmitItemUpdateResult_t)列出主预览图须小于 1 MB。项目选用现有 512×512 封面无损编码为 PNG，检查真实格式、正方形尺寸和小于 1 MiB；原 JPG 保留，未修改任何头像高清 PNG 原件。

首次 1.0 构建错误地输出 `thumbnail.jpg` 并引用 JPG，且工坊主预览实际显示占位图。这是本项目实际缺陷；具体修复前后文件核对和工坊回读见 `data/publication/1.0/`。额外上传图库图片与修正模组的主预览文件是两项不同操作，不能用图库出现 logo 代替修正 `thumbnail.png`。

同次实测：Steam 网页的图库上传说明写每批不超过 8 MB，但选择原始选国截图后，实际弹窗执行了单图 2 MB 限制。保留原始 PNG，另以相同尺寸和取景导出 JPEG（quality 95、无色度降采样）供图库上传；两者 SHA 与用途分别登记。图库导出不进入游戏头像 payload。
