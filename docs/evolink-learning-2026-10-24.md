# EvoLink 接入学习（2026-10-24）

按用户指定，只读学习 `XenoAmess/slay-the-spire-vivhite-mod`，固定 master 为 `94559b5a80ef4bdec8ff8a58042256902d8df713`。本机 `bf-202609141645-5434332d4d`，UTC 15:56 已通过 GitHub connector 读回该分支 SHA。原先检查的 CK3 本地工作区较旧，fetch 后的远端 `f9bf6f675` 中没有找到 EvoLink；用户随后明确改指本仓库。

这次是代码、请求归档和历史实验报告学习，没有读取密钥值，没有调用付费图片 API，没有把其他项目的图片、规则或额度移入 HOI4。HOI4 继续采用既定内置工具；学习外部服务不授权将已被拒的冻结请求改词、换输入或换渠道规避拒绝。

## 已读来源

- [Python 客户端](https://github.com/XenoAmess/slay-the-spire-vivhite-mod/blob/94559b5a80ef4bdec8ff8a58042256902d8df713/tools/art/evolink_transparent_image.py)，Git blob `66b131d901e98c062ca1b31a18b2cd873fcc9aec`；完整读取。
- [原生透明实验](https://github.com/XenoAmess/slay-the-spire-vivhite-mod/blob/94559b5a80ef4bdec8ff8a58042256902d8df713/docs/2026-08-28-EvoLink-GPT-Image-2原生透明实验.md)，blob `dd41d1489f1daf25ca44f18acf2febb1e4d5eb10`。
- [原生透明工具说明](https://github.com/XenoAmess/slay-the-spire-vivhite-mod/blob/94559b5a80ef4bdec8ff8a58042256902d8df713/tools/art/README.md)、付费追加归档说明、Prompt 目录说明、根 AGENTS 的美术规则。
- 第二次身份母版的完整 `output.request.json`；其中模型、完整实际词、两个参考 URL 和参数均有保存。
- [能量小图的 manifest](https://github.com/XenoAmess/slay-the-spire-vivhite-mod/blob/94559b5a80ef4bdec8ff8a58042256902d8df713/assets/vivhite-ironclad/generated/evolink/2026-08-31/energy-text-attempt-01/manifest.json)和相邻 assessment：原始 1024×1024 RGBA8 输出、SHA、实际 Alpha 与静态消费结果。

## 可复用的接入能力

1. 创建：`POST https://api.evolink.ai/v1/images/generations`，Bearer 鉴权。该仓库客户端固定 `model=gpt-image-2`、`background=transparent`、`n=1`；可配置 size、1K/2K/4K、low/medium/high 和多个有序 `image_urls`。命令行允许值是代码能力，不代表每档已经在本机实测。
2. 异步取回：立即记录 task ID，随后 `GET https://api.evolink.ai/v1/tasks/{task_id}`。默认每 5 秒轮询、总等待 600 秒；识别 pending/queued/processing/running 及 completed/succeeded/success。遇明确失败就报告，源码没有自动重复 POST 或绕过内容拒绝的机制。
3. 恢复：`--task-id` 在原 output 路径恢复轮询/下载，不新建生成任务。必须保有原 prompt、去密请求和匹配的 task 侧录，防止下载失败引起重复计费。HTTP 报错、超时与业务失败不能冒充成功；恢复也不等于重新生成失败任务。
4. 实际输入：现成脚本只接受公开 HTTPS 参考图，拒绝带凭据、query、fragment 或临时签名的 URL；不直接接受 Windows 本地路径。迁入 HOI4 前要另行设计获授权的输入传输，不能照抄路径或把完整原版资产公开上传。
5. 完整记录：调用前保存真正发送的 prompt 和去密 request；原图、prompt、request、task 分开保存且拒绝覆盖。源码先对输入 prompt 做 `.strip()`，因此保存的是处理后实际发送的字符串，不能声称和任意含首尾空白的输入文件原字节相同。
6. 密钥：先读进程 `EVOLINK_API_KEY`，Windows 可补读用户级环境，最后隐藏交互输入；密钥不放命令行或归档。学习时只读了实现，没有查询本机密钥。
7. 下载：生成结果链接仅用于取回；下载请求使用 Accept、浏览器 User-Agent 与 EvoLink Referer。历史报告记录这组头解决了当时 CDN 403，并从同一任务成功取回；这不是对所有未来 403 的保证。
8. 文件验收：客户端检查 PNG 签名后保存返回原字节；其本身不检查所有 Alpha/美术条件。真正透明、主体是否近乎不透明、有无可见孔洞或光晕仍须读 RGBA 并实际合成审查。原始 PNG 与游戏派生图分开保留。

## 历史已验证与本次边界

2026-08-28 实验报告记录三次原生透明输出：第一张光晕过大，被该用途拒绝；第二张作为身份根接受；第三张服装偏离设定，仅归档。首张 RGBA8 为 1680×2512，四角 Alpha 为 0、主体约 253、最大 254。这说明服务当时能返回原生透明 PNG，也说明最大 Alpha 254 不能单独证明不合格。这里复核的是原记录，不是本机新一轮生成或美术验收。

能量小图原始 SHA 为 `f2a5f701bf775ede7a132bee3c9b511a22606e6834634dd15f821065fc6ea2a2`，归档记录四角 Alpha `[0,0,1,0]`、边缘最大 1；其用途验收没有仅凭不可见的边缘数值花第二次生成。该仓库为静态小图进行的尺寸适配不自动成为 HOI4 高清游戏输入的缩放例外，也不构成完整实机验收。

该项目“同一语义最多八次调整词的付费尝试”是它自己的美术额度，不可代替 HOI4 每次拒绝后八小时、冻结原请求的服务重试政策。其“透明图唯一 EvoLink”规则也只管该项目；HOI4 用户已经选择的内置工具仍按本项目规则执行。

另读了 [EvoLink 当前官方文档入口](https://docs.evolink.ai/)，入口现已跳转较新的模型页。本文的具体模型和参数结论均绑定上述仓库版本及当时回执，没有把新的型号、价格、余额、吞吐或限流外推为已实测能力。实际采用外部 API 前需要再核对所选路由的当前官方参数；本次没有实施或启动该迁移。
