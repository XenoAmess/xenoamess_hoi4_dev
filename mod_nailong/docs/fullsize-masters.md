# 高清母版与游戏用图

图片工具返回的 PNG 是高清母版。`assets/portraits/` 则按 HOI4 原纹理尺寸生成技术缩放图，例如 156×210、65×67 或 42×46；builder 从这些图编码游戏需要的 DDS。原尺寸便于与原版资源匹配，但缩小图不能替代后续返修需要的高清原件。

此前高清文件仅留在执行机器的图片生成目录，Git 保存缩小图及高清 SHA，没有远端高清副本。2026-10-17 用户指出这一缺口后，新增独立素材附件归档。原 PNG 不缩放、不改编码、不丢透明度；ZIP 使用 stored 条目，只装入原始字节。已被替换版本和实验输出保留真实身份，不冒充当前合格版本。

归档采用本公开 GitHub 仓库的 `art-masters-NNN` 素材附件，明确标为 prerelease / development art archive，与可玩的 mod 版本、Steam Workshop 发布及验收分开。大型附件不进入普通 Git 历史；[GitHub 官方建议用 Releases 分发大型文件](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github#distributing-large-binaries)。没有启用 Git LFS 或图片 API。

执行 `python mod_nailong/tools/master_archive.py inventory` 时，读取当前及历史生成记录、A/B 实验中的高清 SHA，再从本项目回执已证明的生成目录寻找完全匹配的 PNG。其他输出不因出现在同一目录而被收录。不复制、上传原版游戏图片。

执行 `python mod_nailong/tools/master_archive.py archive --tag art-masters-001` 时，冻结待归档清单，排除已有归档的完全相同输出，以流式 ZIP 上传。一次整包传输被本机代理中断后，改为按原 PNG 合计约 32 MiB 分组的独立 ZIP，文件传输最多四路；图片生成仍为一路。每卷都可以单独解压，断线保留已验证卷。计划和各卷索引先冻结，续传复用原计划，不混入随后生成的新图；新图进入下一次归档。

ZIP 不落本地磁盘，读写缓冲为每路 1 MiB，中央目录及小型索引留在内存。生成前、流式发送中分别核对输入 SHA，来源改变即停止。先上传 draft，完整认证下载核对字节数和 SHA 后才公开素材附件，随后刷新公开下载 URL，再完整匿名下载核对。所有卷两次读回都成功才写入 `data/fullsize-archives.json`。上传成功回调不能代替读回。恢复已有卷时，只有先前完整认证下载记录、相同 asset ID / 大小及 GitHub 返回的 SHA 同时吻合，才复用认证读回；匿名下载仍须完成。初次公开后的 draft 占位 URL 已改为从实际发布回执刷新，不能把旧 `untagged-*` 地址当成正式下载地址。

每卷 ZIP 内 `index.json` 保存尺寸、PNG 字节数、SHA、生成 journal / 实验关联及可用的完整 prompt 快照，`png/<高清SHA256>.png` 保存原图。仓库的 `data/fullsize-archives.json` 提供附件下载地址、ZIP SHA 和逐图所属卷。`data/generated.json` 的 `generated_fullsize_sha256` 可直接用于查找当前版本；`revision_history` 与请求 journal 用于查找旧输出、prompt 及实际尝试。归档的 repository base commit 与后续工作树审图分开标注，不声称正在生成的工作树已经存在于旧 commit。

以后每张导入同时保存按输出 SHA 命名的本机定位回执，返修不会覆盖旧母版的位置。本机同卷原 PNG 通过硬链接放入 `assets/generated_fullsize/<高清SHA>.png`，保留实际分辨率与原始字节，禁止原地修改此内容对象。`link-current` 可为已有当前版本补齐。跨卷不能直接使用硬链接时，应先安排复制预算并处理真实失败，不冒充本机方法已在其他机器生效。这个目录在 Git 中忽略，由素材附件提供远端副本。

新图在下一次增量归档完成前明确属于待归档；正常开发交付包括归档、完整远端读回及索引 commit/push。归档资格与美术资格独立，未审图或失败返修不计入合格进度。

直接预览的[罗斯福高清样例](media/fullsize-portrait-example.png)是工具返回的原始 1081×1455 PNG，与 156×210 的游戏用图分别保存；[来源及 SHA](fullsize-portrait-example.json)可核对。普通 Git 只额外保留这一张展示样例，完整母版使用分卷附件。

本机初始清点：`machine_id: bf-202609141645-5434332d4d`，2026-10-17 15:05:30 UTC，证据为项目生成 journal、实验 manifest、本机生成定位回执与逐文件 SHA。509 个已记录不同高清输出全部找回，共 950,919,533 bytes；当前 401 张头像的母版均存在。该数字只描述该次快照，不代表后续输出已经自动归档。实际备份成功时间与附件身份以归档索引为准。

本机原件和缓存继续遵守共享存储策略及有期限的用途复核，不在本次归档中删除。远端副本读回完成也不自动授权回收仍在使用的原件。

已验证归档快照：`machine_id: bf-202609141645-5434332d4d`，2026-10-17 16:03:39 UTC（北京时间 10 月 18 日）：536 个已记录高清输出，合计 1,003,017,026 bytes，现有 418 张头像的母版均有远端副本。[首批 515 张／30 卷](https://github.com/XenoAmess/xenoamess_hoi4_dev/releases/tag/art-masters-001)及[增量 21 张／2 卷](https://github.com/XenoAmess/xenoamess_hoi4_dev/releases/tag/art-masters-002)均完成认证及匿名完整读回。逐图查找、卷 SHA 和核验时间见[归档索引](../data/fullsize-archives.json)，范围及保留复核见[快照](../data/fullsize-backup-checkpoint.json)。后续新增不自动算入这份历史快照。
