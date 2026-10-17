# 高清母版与游戏用图

图片工具返回的 PNG 是高清母版。`assets/portraits/` 则按 HOI4 原纹理尺寸生成技术缩放图，例如 156×210、65×67 或 42×46；builder 从这些图编码游戏需要的 DDS。原尺寸便于与原版资源匹配，但缩小图不能替代后续返修需要的高清原件。

此前高清文件仅留在执行机器的图片生成目录，Git 保存缩小图及高清 SHA，没有远端高清副本。2026-10-17 用户指出这一缺口后，新增独立素材附件归档。原 PNG 不缩放、不改编码、不丢透明度；ZIP 使用 stored 条目，只装入原始字节。已被替换版本和实验输出保留真实身份，不冒充当前合格版本。

归档采用本公开 GitHub 仓库的 `art-masters-NNN` 素材附件，明确标为 prerelease / development art archive，与可玩的 mod 版本、Steam Workshop 发布及验收分开。大型附件不进入普通 Git 历史；[GitHub 官方建议用 Releases 分发大型文件](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github#distributing-large-binaries)。没有启用 Git LFS 或图片 API。

执行 `python mod_nailong/tools/master_archive.py inventory` 时，读取当前及历史生成记录、A/B 实验中的高清 SHA，再从本项目回执已证明的生成目录寻找完全匹配的 PNG。其他输出不因出现在同一目录而被收录。不复制、上传原版游戏图片。

执行 `python mod_nailong/tools/master_archive.py archive --tag art-masters-001` 时，冻结待归档清单，排除已有归档的完全相同输出，以流式 ZIP 上传。整个 ZIP 不落本地磁盘；读写缓冲为 1 MiB，中央目录及小型索引留在内存。生成前、流式发送中分别核对输入 SHA，来源改变即停止。先上传 draft，完整认证下载核对字节数和 SHA 后才公开素材附件，再完整匿名下载核对；两次读回都成功才写入 `data/fullsize-archives.json`。上传成功回调不能代替这些读回。

ZIP 内 `index.json` 保存尺寸、PNG 字节数、SHA 和生成 journal / 实验关联，`png/<高清SHA256>.png` 保存原图。仓库的 `data/fullsize-archives.json` 提供附件下载地址、ZIP SHA 和逐图位置。`data/generated.json` 的 `generated_fullsize_sha256` 可直接用于查找当前版本；`revision_history` 与请求 journal 用于查找旧输出、prompt 及实际尝试。

以后每张导入同时保存按输出 SHA 命名的本机定位回执，返修不会覆盖旧母版的位置。新图在下一次增量归档完成前明确属于待归档；正常开发交付包括归档、完整远端读回及索引 commit/push。归档资格与美术资格独立，未审图或失败返修不计入合格进度。

本机初始清点：`machine_id: bf-202609141645-5434332d4d`，2026-10-17 15:05:30 UTC，证据为项目生成 journal、实验 manifest、本机生成定位回执与逐文件 SHA。509 个已记录不同高清输出全部找回，共 950,919,533 bytes；当前 401 张头像的母版均存在。该数字只描述该次快照，不代表后续输出已经自动归档。实际备份成功时间与附件身份以归档索引为准。

本机原件和缓存继续遵守共享存储策略及有期限的用途复核，不在本次归档中删除。远端副本读回完成也不自动授权回收仍在使用的原件。
