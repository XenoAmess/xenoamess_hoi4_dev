# 图片已返回后的导入恢复

`important-009` 的第 8 张图片已经由内置工具返回，但本地 `finish` 在图片和初步 metadata 写入后退出，journal 仍为 prepared。来源、时间、机器与 SHA 见 [恢复回执](../data/import-recovery-009.json)。原错误输出被截断，根因未确定；不能据此断言 Windows 锁文件或图片服务限流。

恢复复用原先返回的 full-size PNG，没有重新生成、消耗服务拒绝重试次数或增加虚假的美术版本。工具逐项核对原 prompt 文件、full-size SHA、原图 key、规范输出路径、原始尺寸、当前 PNG SHA，以及同一返回图片按既有 RGBA/LANCZOS/native-size PNG 流程重新计算的字节 SHA。只有 pending 且完全一致的部分导入可以补齐 metadata 与 journal；已审图或内容变化时停止并保留诊断。恢复本身不会授予审图资格。

导入先保存外置原件回执，再写完整 canonical row，减少中间状态。共享 JSON 的原子替换对本地 `PermissionError` 做有界短暂重试，持续失败仍抛错并保留上一份完整 JSON；这不构成并发写锁，也不会重试 imagegen。后续 `finish` 错误完整保存到 `runtime/import-errors/<source_sha256>.txt`，调度方应暂停该次导入并检查原输出，避免误记为服务拒绝或重做已返回图片。

18 项测试通过，包含相同输出续接、已变化的部分图片拒绝续接、临时文件替换受拒后的旧记录保护，以及持续受拒时的真实失败。素材审计与确定性双构建同时通过。完整原 prompt 继续按原路径保存，后续图片仍使用内置工具单路生成。
