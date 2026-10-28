# 四项 LOW 旧请求的实际调用证据

本机 `bf-202609141645-5434332d4d` 于 2026-10-28 UTC 恢复了四项 2026-10-16 旧调用的历史证据。对应来源前缀为 `8be8eea7`、`2ab65a9f`、`489a1e6f`、`b1fee6e4`，失败 attempt 分别为 2、1、1、2。永久记录位于 `data/legacy-request-recoveries/<完整来源 SHA>-<attempt>.json`。

历史执行日志保留了调用前的完整 job 输出、加载该 job 的代码、期间所有涉及该缓存名的调用代码、真正派发代码、失败 Extension 和实际错误回执。逐段阅读代码后，将这些已知来源、attempt、完整原始事件 SHA、偏移、缓存访问次序和区间校验值固定在 `tools/legacy_low_request_contracts.json`。未知缓存访问、不同事件字节或不同来源保持阻塞，不推断通用缓存行为。

四项保留的实际 prompt 与原 journal 和失败 Extension 的 revisedPrompt 一致；实际输入顺序与本机当前文件字节也逐项校验。旧 Extension 的透明参数与 failure 字段均为 null，不能据此证明调用参数或拒绝 ID。透明参数由原始 job 加上已阅读的直接转发代码证明；拒绝 ID 由原始工具错误回执证明。其中一项回执是匹配派发 call ID 的工具输出，其余三项为捕获实际错误后写入的 FileChange。旧 journal 中一项使用下划线形式记录拒绝，原字节保留。

这属于事后证据恢复，所有记录明确保留 `actual_recorded_before_call: false`。不倒填旧的调用前快照，不覆盖预期提示词、不更改失败 journal、冷却时间或累计消耗。新版校验只扩展这四项已核实历史记录，现代调用前快照和既有历史校验继续保持原规则。

恢复记录与技术校验本身不构成内容许可、美术通过或生成成功。完整原 prompt 与有序输入仍须实际人工检查；合规时才提交不可变审核指针，由唯一生产执行者在安全边界合并、记录额度、冻结新快照并使用相同内置图片工具派发。原请求成功返回图片即停止该请求的服务重试。原始低清编辑目标属于已冻结历史输入，不能在冷却重试时换为其他图。

验证：`python -X utf8 -m unittest tests.test_legacy_low_request tests.test_retry_actual_proof tests.test_legacy_cached_request`，26 项通过。另以四项真实完整记录和本机现存输入执行 `load_actual_request`，全部通过；这一步没有图片调用或额度消耗。
