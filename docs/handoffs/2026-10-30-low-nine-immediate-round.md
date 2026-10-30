# 剩余 LOW 九项立即尝试结果

机器：`bf-202609141645-5434332d4d`。核验时间：2026-10-29 17:29:31 UTC（本地 2026-10-30）。

用户要求：“现在立刻给我重试这9张。”已对固定九项逐项完成本轮一次内置图片工具调用，全部收取明确终态；实际客户端最大同时挂起数为 1，没有遗留未知结果或仍在调用的 ledger。

| 本轮实际结果 | 数量 |
| --- | ---: |
| 实际调用 | 9 |
| 输出阶段服务审核拒绝 | 9 |
| 返回原始 PNG | 0 |
| 网络或其他错误 | 0 |
| 新增审图通过 | 0 |

九条实际回执均为 `moderation_blocked`，`moderation_stage=output`，带 `safety_violations=[abuse]`。保留各自不同的 request ID 和完整原始错误；这不证明具体审核原因或服务故障。

七项原本已经耗尽八次累计重试，各追加一次授权并实际消耗，现均为 9/9。已有请求保持完整原 prompt、原输入字节/顺序及透明参数，不改词、不改色、不换图、不换服务。`03d0…` 上一轮的实际网络错误保持原记录，经严格核验原 ledger、快照和本轮首条真实 HTTP 终态后才恢复准入；它本轮的新结果才是审核拒绝。

另两项 `13714c…`、`9e6fa7…` 此前没有实际调用，因此本轮各为首次调用，不虚报为历史重试。已逐图查看精确原图与角色参考、记录完整新提示词，再依据本次明确范围覆盖项目的原资产路径保护。未解除任何同人物服务保护，也未删除或伪造原拒绝。二者当前累计重试已用仍为 0，不能说这两项已耗尽；本轮要求的每源一次已经完成。

当前 HIGH 覆盖 4,535/4,535（含 4 个保留原图例外），LOW 仍为 694/703，整体覆盖 5,229/5,238（99.83%）。生成 manifest 与母版索引完整 SHA 均与本轮前一致。

21 项相关测试通过，模拟测试不计入九次真实调用。额度加载器移除了“所有授权必须恰好 31 项”的旧写死条件，继续校验授权文件 SHA、准确非空数量、逐来源身份和只追加一次；默认八次及既有 HIGH 31 项授权不变。

逐项完整 prompt、输入 SHA、真实 UTC、request ID、原始错误和调用证据见：

- `mod_nailong/data/extra-retry-rounds/20261030-remaining-low-nine-one-immediate-round.json`：固定授权与变更前队列。
- `mod_nailong/data/extra-retry-rounds/20261030-remaining-low-nine-one-immediate-round-completed.json`：九项实际完整结果。
- `mod_nailong/data/extra-retry-rounds/20261030-remaining-low-nine-one-immediate-round-validation.json`：21 项测试结果。

`runtime/low9-round-20261030/` 的实际错误、job 和调用前备份，以及 `runtime/dispatch-actual/low9-20261030-*.json` 的实际发送快照保持本机活跃引用。所有已领取计数均能对应本轮实际完成调用，没有只准备未调用的新增尝试。

用户暂停 Git 的要求继续有效，本轮 Git 命令为 0，未提交或推送本轮修改。未调用 EvoLink、CLI/API 图片生成、游戏或 Workshop。
