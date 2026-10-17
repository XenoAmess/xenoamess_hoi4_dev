# 法国首批实际提示词的传输更正

2026-10-18 北京时间，`machine_id: bf-202609141645-5434332d4d` 在核对完整实际 prompt 时发现：法国 important-015 的 17 次首发请求，通过 Python 默认 CP936 标准输出读取 JSON，而执行工具按 UTF-8 解码。中文标签“奶龙”因此变为四个 `U+FFFD`。实际发送到内置图片工具的 JS 字符串与请求前保存的预期文本不完全相同。

这是此前的传输校验遗漏。不能把预期文本继续冒充实际调用词，也不能补写后声称当时已完成全部实际文本的调用前记录。现已从串行执行器保留的 17 个实际 JS job 对象恢复完整发送文本，另存 `assets/prompts/*-001-actual-transport.txt`，把 journal 的实际 prompt / 文件 / SHA 指向这些恢复文件；预期原稿及其 SHA 保留在 `intended_prompt*` 字段，原文件不改写。每条明确标注 `actual_recorded_before_call: false`、恢复时间和证据快照 SHA。详情见[逐请求更正记录](../data/prompt-transport-correction-015.json)。

其中 16 次返回图片，1 次 Darlan 服务拒绝；拒绝原文、request ID、实际输入、冷却截止和重试消耗均不因本次更正改变。若未来原样重试，应使用恢复的真实发送词，包括原请求中的替换字符，不能借纠正中文改写被拒请求。三次后续领口返修使用纯英文，实际文本与预存文本一致。核对保留的 important-009 至 014 共 151 个 job 对象未发现这种替换字符。

这些调用的英文指令、原图和用户参考图 SHA 均未改变；此次没有改动、重新生成或重新计数图片，既有视觉审查仍绑定相同 PNG SHA。当前图与被替换图的 prompt 关联、Darlan 失败记录也已一起更正。

高清归档 `art-masters-002` 内的 PNG 字节及 ZIP SHA 仍正确。该次法国首发的 ZIP prompt 快照保存的是当时预存的预期文本，应以本更正及其实际 prompt 文件为准。原 ZIP 保留不覆盖；归档索引与附件说明追加此更正，不把历史元数据静默换成另一份。

后续使用 `production_queue.py export-job` 输出 ASCII 转义 JSON，客户端 `JSON.parse` 恢复原始 Unicode。调用前，JS 执行器把**将实际发送的完整 job**保存为 UTF-8 请求快照，再交给 `begin --actual-job-file` 与冻结 journal 的 prompt / 输入 SHA 核对；只读取原 job 文件不足以证明跨进程传输无损，缺少实际快照时拒绝派发。新增测试实际模拟 CP936→UTF-8 破坏并确认拒绝派发，同时验证 ASCII JSON 往返后文本完全一致。
