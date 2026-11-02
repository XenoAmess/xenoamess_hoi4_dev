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

下一组四份真实任务完整返回后，累计为 **37 次实际调用、36 份完整候选、1 份截断整弃、0 次 HTTP 重试**。owner 逐项核对原始资源与转换 PNG 的两种 SHA，将前两项“开领或闭领”改为原图明确的闭合立领，并补齐各自毛发、表情和领口约束后部分采用。两张同路径、不同 SHA 的来源继续独立准备；[共享回执](https://github.com/XenoAmess/local-model-operations/blob/af50e4c47b23e9eef7d3c20c23bd3d5e260bd182/docs/evidence/2026-11-02-hoi4-b017-prompt-followup.json)保留此待调用截止，不追认图片生成或视觉资格。

再后四份任务同样完整返回，累计 **41 次真实调用、40 份完整候选、1 份截断整弃、0 次 HTTP 重试**。owner 比较小卡原始像素与四张大图，排除朝向或发型、服装不同的候选；部分采用前把含糊开闭领改为原图的开襟西装，把一项过强的无胡须断言恢复为小像素细节的真实不确定性。另一张明确的长灰白胡须、圆框眼镜仍完整保留，不将细节不确定性跨人物套用。[共享回执](https://github.com/XenoAmess/local-model-operations/blob/c3a8756f9667ad93b53bb7f718058b20a15e133f/docs/evidence/2026-11-02-hoi4-b018-prompt-followup.json)只记录待调用文本及实际采用边界。

随后四份真实任务完整返回，累计 **45 次调用、44 份完整候选、1 份截断整弃、0 次 HTTP 重试**。owner 补回第二份候选漏掉的绿色眼圈，并收窄含糊的条件毛发措辞；第一份正确保留了深紫/灰背景，尽管 owner 通用合同误写了灰背景。该输入冲突记录为 owner 原因，最终实际图片词以逐源背景为准，不归咎模型。两种 SHA 与实际输入角色仍另验；[共享回执](https://github.com/XenoAmess/local-model-operations/blob/25ce7d51f2cadb2cd483d9591037989235feb673/docs/evidence/2026-11-02-hoi4-b019-prompt-followup.json)只授予部分文本采用，不授予图片资格。

下一组完整返回后，累计 **49 次调用、48 份完整候选、1 份截断整弃、0 次 HTTP 重试**。owner 明确区分闭合金绣立领与开襟西装，删除隐藏花饰的条件提示及非输入大图、其他人物提法，保留小卡实际遮挡边界。本组通用输入已使用原图确切背景色，修正前批灰背景假设；旧实际发送记录保持原样。[共享回执](https://github.com/XenoAmess/local-model-operations/blob/c866428ec00dfd903aabf3a2b9ba5dd197bc5746/docs/evidence/2026-11-02-hoi4-b020-prompt-followup.json)记录逐项部分采用和成本未知项，实际图片另审。

随后四份任务完整返回，累计 **53 次 HTTP 调用、52 份完整候选、1 份截断整弃、0 次 HTTP 重试**。owner 区分白色闭领海军制服与开襟外衣，保留正式翼领/领巾与普通领带的差别；白色原衣物不能当作奶龙肚皮删除。两种 SHA 另验正确，明确开闭领并删掉非输入大图提法后部分采用。[共享回执](https://github.com/XenoAmess/local-model-operations/blob/15534796f6b15ac46ee3cfafe66deaedbc126d25/docs/evidence/2026-11-02-hoi4-b022-prompt-followup.json)保留待调用截止。图片服务后来实际发生的拒绝另记在图片请求账本，不计作本地文本模型的 HTTP 失败或重试。

再后四份任务完整返回，累计 **57 次 HTTP 调用、56 份完整候选、1 份截断整弃、0 次 HTTP 重试**。owner 保留领结、分层白裹领布、短完整胡须、下垂白色上唇胡须与小块浅色下巴毛发的逐源区别，排除同名不同军服版本。删掉第二份夹带的协议说明和第三份借用其他衣服的提法，核对两个 SHA 域并明确开襟外衣和各自领部布料后部分采用。[共享回执](https://github.com/XenoAmess/local-model-operations/blob/467e97e9c66b421921ec215ad6c425177e24f00d/docs/evidence/2026-11-02-hoi4-b023-prompt-followup.json)保留四份未调用文本的真实截止，实际图片资格另审。

随后四份任务完整返回，累计 **61 次 HTTP 调用、60 份完整候选、1 份截断整弃、0 次 HTTP 重试**。owner 查看四张小卡及三张大图候选，逐源保留白领结与金链、封闭立领军服、近侧脸无法分清的深色领饰，以及棕色开襟西装。开闭领泛化措辞改为实际服装状态；两个 SHA 域、朝向及真实不确定性另验后部分采用。[共享回执](https://github.com/XenoAmess/local-model-operations/blob/664a6c4b6fe72072a3a83a2f8ba440e133eeadcf/docs/evidence/2026-11-02-hoi4-b024-prompt-followup.json)保留未调用文本截止。11月3日本机每日检查复用了当天00:03已成功的共享缓存，OpenCode及registry最新均为1.19.5；未触发新的业务请求或旧任务重投。

11月3日下一组四份真实任务均完整返回，累计 **65 次 HTTP 调用、64 份完整候选、1 份截断整弃、0 次 HTTP 重试**。owner 对照四张小卡及五张大图候选：含两个人名的文件实际只有一人，被便笺遮住的服装不从另一画像补造；较窄的53×65卡片没有便笺，保留实际浅蓝绶带和金绣立领。删去其他画像/服装提法及泛化开闭措辞，补回第二份遗漏的眉毛，并另验两个SHA域后部分采用。[共享回执](https://github.com/XenoAmess/local-model-operations/blob/a67f97641f8958c49f3b4868714bca384888f598/docs/evidence/2026-11-03-hoi4-b025-prompt-followup.json)保留四份未调用文本截止；实际图片仍按各自原图、母版和透明通道逐张验收。

随后四份任务完整返回，累计 **69 次 HTTP 调用、68 份完整候选、1 份截断整弃、0 次 HTTP 重试**。owner 对照明暗各异的小卡与四张大图候选，保留圆镜、斑点围巾、宽檐帽与烟斗；同路径不同SHA各自生成。第四份候选漏掉帽子和眼镜，已按实际来源补回；第二份协议说明已删。owner通用输入误把围巾也带入男性版本，另行收窄为实际外套、衬衫和领带，不归作模型独立捏造。两个SHA域及原图曝光另验后部分采用，[共享回执](https://github.com/XenoAmess/local-model-operations/blob/49eea143baff2c083671766ee7768852f2c2f91b/docs/evidence/2026-11-03-hoi4-b026-prompt-followup.json)保留未调用截止。上一组实际图片有长椭圆下半脸问题，已拒绝并准备内置工具返修；文字采用不抵扣图片资格。

再后四份任务完整返回，累计 **73 次 HTTP 调用、72 份完整候选、1 份截断整弃、0 次 HTTP 重试**。三份提示词部分采用；第二份虽然传输完整、两个SHA正确，却只重复通用合同，遗漏输入已明确提供的帽子、毛发、制服和颈部饰物等逐源事实，并夹带协议说明，已拒绝。owner按原合同和真实观察完整重建该词，该项语义模型采用为零。其余三份补齐角度、闭口表情及可见衣物细节，仍不从大图移入便笺遮挡的饰物。[共享回执](https://github.com/XenoAmess/local-model-operations/blob/6953af0cf8dd6ae5339c3ba00448ba1dc8768ed3/docs/evidence/2026-11-03-hoi4-b028-prompt-followup.json)记录实际采用差别；72份完整候选不代表72份可用产物。

下一组四份任务完整返回，累计 **77 次 HTTP 调用、76 份完整候选、1 份截断整弃、0 次 HTTP 重试**。owner实际查看四张小卡与五张大图候选，保留同路径明暗叶冠/长胡须版本及旧版海军近侧脸。将owner通用输入中的敞开制服或闭合金领条件收窄为逐源实际状态，补回第四份候选漏掉的深蓝金带檐帽和朝左方向后部分采用。两个SHA域另验，[共享回执](https://github.com/XenoAmess/local-model-operations/blob/1198322687553b4dd8111d4c9142de14fd09fcde/docs/evidence/2026-11-03-hoi4-b029-prompt-followup.json)保留四份未调用文本截止。极暗原图保留原光照，文字和传输成功继续与图片资格分别记账。

又一组四份源图合同完成本地模型传输与人工文本复核，累计 **81 次真实 HTTP 调用、80 份完整候选、1 份截断弃用、0 次 HTTP 重试**。逐源提供开襟／闭合服装合同；owner 补回第二份候选遗漏的圆框眼镜，删除第四份对非输入大图的额外讨论，保留上唇与眼镜细节确实难辨的证据边界。四份最终提示词仅部分采用模型候选；图片仍需实际生成和逐图审查。[固定提交回执](https://github.com/XenoAmess/local-model-operations/blob/d89fb0b2c8f2f68955966ce27f6f1e9998615c54/docs/evidence/2026-11-03-hoi4-b030-prompt-followup.json) 已公开原始字节读回。该回执冻结于四项尚未派发的真实时间点；Git 网络恢复期间生成可继续，根项目使用此前冻结的请求日志字节提交这一准备状态，不倒写后来的调用结果。共享仓库首次推送失败后以普通推送恢复并核对实际远端 SHA。
