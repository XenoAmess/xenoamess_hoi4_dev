# 本地模型接入

2026-11-02 用户要求实际大量使用本地模型，并把既有经验迁移到共享仓库。父目录的 `local-model-operations/` 是当前规范与调用器来源：[共享 AGENTS](https://github.com/XenoAmess/local-model-operations/blob/main/AGENTS.md)、[使用方法](https://github.com/XenoAmess/local-model-operations/blob/main/docs/usage.md)、[配置](https://github.com/XenoAmess/local-model-operations/blob/main/config/executor.json)。每次执行记录实际共享版本及文件 SHA，地址和协议随该配置读取。

在共享仓库运行 `python -X utf8 scripts/check_opencode.py` 完成当天检查。HTTP 任务通过其 `scripts/call.py` 发出，完整源码/合同与具体任务分别冻结，候选由 owner 核对身份、路径、来源和语义后应用。原始材料保存在本项目已忽略的 `runtime/local-model-operations/`。

本项目的 [Windows 启动修复历史](maintenance/opencode-windows-repair-2026-10-25.md) 已迁入共享仓库的历史区，并提炼为 [Windows 客户端经验](https://github.com/XenoAmess/local-model-operations/blob/main/docs/hoi4-windows-client-experience.md)。历史仅证明当时指定 Windows/pnpm/OpenCode 版本的 CLI 加载与分派；实际模型调用和本次每日升级分别记录。

本地模型适合当前代码、文档、库存与提示词文本工作。来源标识与合同核查使用真实提供的数据，模型输出的 SHA 或路径必须另验。图片仍逐原图由内置工具生成，人工实际查看原图、完整母版和白底/青底/alpha 后作出 SHA 绑定决定；本地文本候选不授予视觉资格。
