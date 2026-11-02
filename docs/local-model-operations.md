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

2026-11-02 接入阶段已实际完成 17 次共享 HTTP 调用：16 份完整候选、1 份 length 整弃、0 次 HTTP 重试。规则、历史和提示词分别记录实际采用；两轮适配器代码/测试候选拒绝后由 owner 接管实现，11 项边界测试通过。首批实际客户端峰值为 9，持续 30.866055 秒；不据此推断服务容量或节时。逐项采用、失败与成本未知项已发布到[共享案例](https://github.com/XenoAmess/local-model-operations/blob/a4817d9095f66d7a983f30dbc87187836d86f3d7/docs/hoi4-model-operations-2026-11-02.md)及其脱敏回执。旧 Windows 文档在固定公开 commit 的原始字节已完整读回核 SHA；原始请求、响应与机器账本继续留在本机忽略目录。

随后两组各四项实际提示词任务均完整返回、无 HTTP 重试，累计达到 25 次真实调用、24 份完整候选及 1 份已弃用截断。owner 逐项检查两种 SHA、实际输入角色、发型、衣领、眼镜、木偶与表情，删去协议措辞并补齐原图约束后部分采用。后到记录分别见[首组](https://github.com/XenoAmess/local-model-operations/blob/0fe3600c8ab228486edecb107ebbcf0b267fa6ea/docs/evidence/2026-11-02-hoi4-prompt-text-followup.json)和[次组](https://github.com/XenoAmess/local-model-operations/blob/13530f90d31c5fbb19005b4c7b671e55aaa5290d/docs/evidence/2026-11-02-hoi4-accessory-prompt-followup.json)。实际图片曾把 owner 原始观察中的“footprint（占据区域）”画成脚掌，已审图拒绝并另排明确措辞的局部返修；输入歧义、文本采用和图片资格分别记录。

再后到四份独立原图提示词任务均完整返回，累计 **29 次真实调用、28 份完整候选、1 份截断整弃、0 次 HTTP 重试**。owner 排除朝向、衣服或发型不匹配的大图后提供实际小卡观察；两种 SHA 另验正确，候选经删除无关条件句、修正布料关系和补齐圆下巴/短宽领口约束后部分采用。来源观察与待调用请求随本项目 `5208e0a53` 提交保存；[共享回执](https://github.com/XenoAmess/local-model-operations/blob/6aeff55b82a7cdbe9f3adcf25f91211db735b8b6/docs/evidence/2026-11-02-hoi4-primary-source-prompt-followup.json)已发表并完整读回。历史截止不回写，后续实际图片继续独立验收。

随后四份逐源表情/服装任务均完整返回，累计达到 **33 次实际调用、32 份完整候选、1 份截断整弃、0 次 HTTP 重试**。同一路径下两个不同原始 SHA 的版本分别准备，保留各自发型与领带；微张嘴与闭嘴表情逐源指定。owner 删除候选夹带的协议、非输入及其他来源提法，核对两个 SHA 域后部分采用。该阶段的[共享回执](https://github.com/XenoAmess/local-model-operations/blob/cc26764e15fc2ea26238a2adbcae0bd2007c22bf/docs/evidence/2026-11-02-hoi4-b015-prompt-followup.json)只记录四份待调用文本，不授予图片资格。
