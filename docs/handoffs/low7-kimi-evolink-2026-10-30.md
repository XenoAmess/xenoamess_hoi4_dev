# LOW7：Kimi 的 EvoLink 生成、审图与素材交接

机器：`bf-202609141645-5434332d4d`。范围仅为用户指定的 [七项耗尽 LOW 交接](2026-10-30-low7-exhausted.md) 中的 **7 个不同原始 SHA、10 个游戏资源实例**。不包含九项批次中的另外两项，也不扩展到其他 LOW。

## 实际完成范围

- 7/7 个来源均已通过 EvoLink 实际生成、逐图人工审图并批准，当前批准母版均为 1776×2368 RGB 不透明 PNG。
- 共创建 9 个实际生成 task：首轮 7 个、可见美术缺陷返修 2 个。第 6 项一次连接重置后只恢复原 task，没有新建生成任务。没有遗留未知生成调用。
- 两个首轮返图因可见缺陷被保留但拒收：第三项多出一条嘴状线，第四项虚构胡须；对应返修已分别消除这些缺陷。
- 正式素材入口是 `mod_nailong/experiments/evolink-low7-20261030/approved-masters.json`。其中有逐源原始资产、最终母版、task、实际 prompt、输入顺序、请求、执行、审图和证据 SHA。
- `mod_nailong/data/generated.json` 是正式生产 manifest；本任务的 7 行按 `source_sha256` 接入，绑定 `hair-features-v1` 与 `collar-fit-v1` 的当前 SHA 人工批准。高清母版直接作为后续 builder 输入，不先缩小或模糊。
- 本交接不声称 HOI4 实机验收、全量 LOW、全人物 release 或 Steam Workshop 已通过。后续构建、显示适配与纯 OCR＋键鼠实机验收由 Codex 负责。

## 当前批准母版

| 来源与资源 | 原始 SHA | attempt / task | 批准母版 SHA-256 |
| --- | --- | --- | --- |
| 陆军通用 1 / 9（base） | `6152f2a297cbb891e87a6133bf25401adbc091661a2a20b65eaa10c11ecf57a1` | external-01 / `task-unified-1793297697-c2ao8b73` | `98b7bcfb61802bf5bd34e70188881fb0891cbc81c90e4450aaf93f672380e143` |
| 陆军通用 2（base，单片眼镜） | `03d0c323d5b22aad8f63643c536a368264714ae136359a13e671a8645dc54e1f` | external-01 / `task-unified-1793297827-gex927eb` | `5a2d771d8332d512c6287e1899f13b2fd1cfc8414c215c76760853187dda4f65` |
| 陆军通用 4 / 8（base） | `992fd164fd779b10388e3019ff930a9fc3f6b63794df1997709528ffec1a9cdc` | external-02 / `task-unified-1793299048-2qaar318` | `8e3ef2330f6f1a66cf36785c82f1e59a2dd40e39ea2c35332dd9238d073791a6` |
| 陆军通用 5 / 7（base） | `31205e7b1ce58b6b6ff24c8d2241a15bc5f45c698b214f93d1bddbb4e28331f6` | external-02 / `task-unified-1793299137-h9g5t46v` | `853c8452170581e67893ae8ba05dbadcb0efc7b43cd7d8eaf5c8c9fb433cedcc` |
| 陆军通用 7（By Blood Alone DLC） | `cfabfc9bbcc30771e9e6091c47e71666717cf34e8a25952470128d2d0fdd9749` | external-01 / `task-unified-1793298059-ecf9iluy` | `b29fd33659a6de8305448e73560bae3a352b6a3695e02754de1c6a1b1bb0d318` |
| 海军通用 2（base） | `1f66d040d3ea98c01ad0d0c91bc6a150d379c89d2a4840f604bad60984cab616` | external-01 / `task-unified-1793298130-9wjpywbt` | `b025c45f1e4eefd52d4e43d600a6be1f82b65ce8fa53ef822c48ae3aa2a7b1e1` |
| 海军通用 3（base） | `34e4fe5920a636af439cd8f10154dd6f113b4b2c3184df5d8d005f1049170214` | external-01 / `task-unified-1793298492-wloz6kzf` | `a0906b49005867c4496f99cbc5629aea284981d30c741a35611fdb525327be6b` |

原版 `land_7` 与 DLC `land_7` 的原始 SHA 不同，不能合并。相同原始 SHA 的多个游戏路径共用一次真实生成。

## Codex 应读取的文件

| 内容 | 路径 |
| --- | --- |
| 最终批准母版及完整逐源绑定 | `mod_nailong/experiments/evolink-low7-20261030/approved-masters.json` |
| 原始高清 PNG | `mod_nailong/assets/generated_fullsize/<输出SHA256>.png` |
| 正式生产 manifest | `mod_nailong/data/generated.json` |
| 母版总索引 | `mod_nailong/data/fullsize-files.json` |
| 每源完整历史与新外部调用 | `mod_nailong/data/generation-requests/<源SHA256>.json` |
| 首轮实际输出、prompt/request/task/result | `mod_nailong/experiments/evolink-low7-20261030/outputs/` |
| 两次返修的实际输出及请求 | `mod_nailong/experiments/evolink-low7-20261030/repair-outputs/` |
| 逐图人工批准或拒收理由 | `mod_nailong/experiments/evolink-low7-20261030/review*-agent.json` |
| 白底／青底／Alpha 对照与证据 | 同目录 `review*.png`、`review*-evidence.json` |
| 所有已审输出（含被拒收旧版） | `mod_nailong/experiments/evolink-low7-20261030/outputs-index.json` |
| 本次用户授权及后来的 Git 恢复授权 | 同目录 `authorization.json`、`delivery-authorization.json` |
| 执行工具快照 | 同目录 `tools/`；运行依赖项目的 `runtime` 工具副本，不是无依赖独立程序 |

两张返修前的原始 PNG 仍保留，SHA 分别为 `a27abdb50df7e7a58a2e9a56b10160dd9a21a1208f6fba100d3e07f077ce7222` 和 `b4e1cded371d0bb446044b33e8f53a97c3f2ca8e21ca7fcf4d3b3e8b07cdb03f`，不得误当当前批准版本。海军第 2 项更早的内置返图 `fca9eca6c6b5bfc340b9b931f88abc0b1af0a23cb870fadd823eb6663d1b6614` 也保留在修订历史中。

## 权限、输入与验证边界

- 用户本次明确允许 **Kimi** 对这 7 项使用 EvoLink。没有修改权限文档，也没有赋予 Codex EvoLink 使用权限；Codex 不应调用 EvoLink 重做这些图。
- 原内置工具 9/9 的累计次数、拒绝回执、完整原 prompt 和历史输入均保留。新的 EvoLink 生成与可见美术返修单独记录，不伪装成内置服务重试成功。
- `evolink-low7-source-20261030` 只包含 7 张转换后的单张原图参考；`evolink-low7-repair-input-20261030` 只包含 2 张实际拒收的高清编辑输入。它们不是模组发布、完整游戏资产或母版归档的替代品。母版仍须保留为普通 Git PNG 文件，不使用 LFS。
- 两张返修均采用“实际拒收高清图→精确原图→用户角色参考”的三输入顺序；海军第 2 项保留既有三输入眉毛返修关系。
- `runtime/low7-evolink-20261030/final-verification.json` 保存生成与逐源审图核验；`runtime/low7-evolink-20261030/import-receipt.json` 和远端读回回执保存后续实际提交结果。`runtime/` 是本机执行证据，不是跨机素材依赖。
- 执行回执中继承的 `naiwa-evolink-high131-execution-v1` 是共享 runner 的 schema 标签，不表示这些 LOW 来源已完成 HIGH 正式导入；实际 LOW 范围以 source SHA、scope 和正式 LOW manifest 为准。
- 主工作区有其他执行者的改动。不得整目录提交、stash、reset 或移动主分支。只提交本任务文件，普通 fast-forward push；远端固定提交的原始 PNG 读回不能由本地文件检查代替。
