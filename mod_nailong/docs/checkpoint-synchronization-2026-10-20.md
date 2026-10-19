# 连续生产期间的 Git 同步

本机 `bf-202609141645-5434332d4d`，2026-10-20（北京时间）的实际开发记录。持续生成会在检查期间给新请求日志追加调用前验证。一次检查完成审计、四来源确定性预览验证及本地提交 `c15ccf925e38246ca16d2fd6328a9070837d9a14` 后，生产工作区已有随后写入的请求日志，因此 `git rebase origin/master` 拒绝继续。该次 rebase 失败时尚未推送，不能把之前的本地 commit 当作已交付。五份已经实际返回的图片均先入库，再从原批次仅选尚未调用的 31 项继续；没有重发前五项。

同步现由 [isolated_production_sync.py](../../tools/isolated_production_sync.py) 在独立的 detached worktree 执行。仍先 `git fetch origin`，再 `git rebase origin/master`，仅允许已验证 commit 保持相同 SHA 且可普通快进的结果进入发布；远端变更若产生不同 SHA，须先验证新结果，不能直接当作原已验证提交推送。生产工作区不会被 stash、reset 或 rebase，当前调用和随后入库可继续。

该工作树只检出 `AGENTS.md`、`README.md`、`.gitignore`，复用已有 Git 对象，不检出数 GB 的原始 PNG。`worktree add --no-checkout` 后须在稀疏规则生效时用 `read-tree -mu HEAD` 初始化索引；缺少此步骤的首次本地试验因空索引未通过 clean 检查，保留了失败回执，并未提交任何删除或改动生产工作区。修正后实际 rebase 返回 `HEAD is up to date.`，固定提交 SHA 未变。

[四项检查](../../tests/test_isolated_production_sync.py)已在本机通过，包含真实小型 Git 仓库：生产工作区带未提交写入，隔离树索引正确且不复制资产；另检查重写后 SHA 需重新验证、路径不能逃出限定目录，以及不对生产树执行 stash/reset/rebase。模拟检查不冒充真实仓库同步；本次真实同步回执另有机器、实际 UTC 与固定 SHA。

恢复提交随后已于 `2026-10-19T20:56:17.825247+00:00` 普通快进推送，2787 份原始 PNG、5,267,175,232 字节于 `20:57:38.242959` UTC 完成固定提交远端核验。原先粗略的错误时间文本不作为可靠回执时间；结构化恢复记录保留后来的真实观察时间，并明确没有补写精确失败完成时刻。详见[恢复记录](../data/checkpoint-sync-recovery-2026-10-20.json)与[当前远端原图记录](../data/fullsize-git-checkpoint.json)。该提交之后的生产结果仍须后续提交、推送与原始 PNG 核验，不能计为本次已交付范围。
