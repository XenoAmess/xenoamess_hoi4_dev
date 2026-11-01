# 本地模型接入

2026-11-02 用户要求实际大量使用本地模型，并把既有经验迁移到共享仓库。父目录的 `local-model-operations/` 是当前规范与调用器来源：[共享 AGENTS](https://github.com/XenoAmess/local-model-operations/blob/main/AGENTS.md)、[使用方法](https://github.com/XenoAmess/local-model-operations/blob/main/docs/usage.md)、[配置](https://github.com/XenoAmess/local-model-operations/blob/main/config/executor.json)。每次执行记录实际共享版本及文件 SHA，地址和协议随该配置读取。

在共享仓库运行 `python -X utf8 scripts/check_opencode.py` 完成当天检查。HTTP 任务通过其 `scripts/call.py` 发出，完整源码/合同与具体任务分别冻结，候选由 owner 核对身份、路径、来源和语义后应用。原始材料保存在本项目已忽略的 `runtime/local-model-operations/`。

本项目的 [Windows 启动修复历史](maintenance/opencode-windows-repair-2026-10-25.md) 已迁入共享仓库的历史区，并提炼为 [Windows 客户端经验](https://github.com/XenoAmess/local-model-operations/blob/main/docs/hoi4-windows-client-experience.md)。历史仅证明当时指定 Windows/pnpm/OpenCode 版本的 CLI 加载与分派；实际模型调用和本次每日升级分别记录。

本地模型适合当前代码、文档、库存与提示词文本工作。来源标识与合同核查使用真实提供的数据，模型输出的 SHA 或路径必须另验。图片仍逐原图由内置工具生成，人工实际查看原图、完整母版和白底/青底/alpha 后作出 SHA 绑定决定；本地文本候选不授予视觉资格。

## 并行调用入口

`tools/local_model_batch.py` 是本项目的薄适配器，直接委托共享调用器。plan中的每个任务给出唯一 `task_id`、`spec` 与新 `output`；路径相对plan目录，输出须在 `runtime/local-model-operations/` 内。spec使用共享格式的 `stable_source_path` 或 `source_files`、`task_path` 与有限 `max_tokens`。适配器先验证整个plan、冻结真实输入，再运行每日维护和独立子调用；候选不会自动执行或采用。

```text
python -X utf8 tools/local_model_batch.py runtime/local-model-operations/<batch>/plan.json --machine-id <本机ID> --owner <本任务owner> --jobs 4
```

示例中的材料、身份和新输出目录须换为本次实际任务。运行只打印批次回执位置；维护诊断见回执的 `maintenance_log`，返回75时宿主AI继续读取诊断、自主修复并复查。模型传输、实际采用、软件测试和图片资格各自记账。共享配置、调用器和检查器的实际SHA随批次保存；原始材料继续留在本机忽略目录。

共享仓库已有 [Civ6经验迁移](https://github.com/XenoAmess/local-model-operations/blob/main/docs/civ6-experience-2026-11-02.md)及其固定来源档案；本项目沿用其中可复用的输入、证据和纠错经验。项目原生接口、运行权限和历史采用结论按各自原范围保留。
