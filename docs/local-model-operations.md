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

下一组四份真实源图任务完成后累计 **85 次 HTTP 调用、84 份完整候选、1 份截断弃用、0 次 HTTP 重试**。第二份候选漏掉实际金色细框眼镜与眉毛，第三份漏掉帽子和原小卡朝向，owner补回后部分采用；第四份只有通用合同及协议话语，整份拒绝并接管完整提示词，该份没有语义采用。三份部分采用与一份拒绝分别记账。海军大图与小卡朝向相反，仅作外观分析，小卡实际服装与可见饰物为准。[固定公开回执](https://github.com/XenoAmess/local-model-operations/blob/29e92b95699d58108e815c9b7edbdd565b133916/docs/evidence/2026-11-03-hoi4-b034-prompt-followup.json) 已逐字节读回，仍只证明文本工作。另保存北京时间05:59进度快照：5311/5481合格，96.8984%，本轮76/246；全轮实测约2.745张/小时，预测采用2–3张/小时，两个服务拒绝来源保留在未完成分母。

再完成四个真实源图文本任务，累计 **89 次 HTTP 调用、88 份完整候选、1 份截断弃用、0 次 HTTP 重试**。第二份漏掉绿金大檐帽，第四份漏掉帽子和原图朝左侧面，owner补回并删去协议/哈希尾句后部分采用；第三份的“光头但戴帽”措辞冲突由owner输入，最终规范为戴实际绿色尖顶便帽，原始HTTP输入不倒改。四份均只部分采用；同路径不同原始SHA的卡片仍分别准备。[固定公开回执](https://github.com/XenoAmess/local-model-operations/blob/1271a8b8dd8995d715843951f41e99df7a27f0b2/docs/evidence/2026-11-03-hoi4-b035-prompt-followup.json) 已读回原始字节。另归档固定头像提交1b5ca94a4的完整原件证明：7524份PNG、15583770964字节；原有7517份仅在远端树中确认不可变Git blob、路径和字节数相同后复用既有完整读回，新增7份实际下载并核对SHA。原件归档数不等于合格来源数，后续输出未冒充已在该固定提交验证。

对既有B029/B030案例追加了[实际图像审查后的源观察经验](https://github.com/XenoAmess/local-model-operations/blob/fe774807f2703e54b8f7fe78b7f518d2aab1ec82/docs/evidence/2026-11-03-hoi4-owner-source-omissions-followup.json)：owner文字观察分别漏掉原小卡蓝金饰物、把金白竖向胸饰简化成纽扣；与文本候选漏眼镜等问题分开记账。内置图片工具确实得到原图，输入遗漏与结果缺陷的配对观察不证明唯一因果；本地文本模型没有像素，不能要求其恢复未提供的视觉事实。原请求、输入、PNG、既有案例截止均保留，另排美术返修。补充文档新增HTTP请求为0，累计仍为89次实际调用。共享回执和消费仓库固定47a6710b3提交中的两份实际审查JSON均已读回原始字节。

后续四份源图合同完成真实本地模型调用，累计 **93 次 HTTP 请求、92 份完整候选、1 份截断整次弃用、0 次 HTTP 重试**。四份均部分采用：owner 明确小图实际向左的方向边界，保留真实红领章、裸头波浪发与白色敞领衬衫／无领带状态，保留细眼镜／上唇细节确实难辨的限制，并在生成前规范 owner 的 downward 拼写。候选不承担视觉审图。[固定提交回执](https://github.com/XenoAmess/local-model-operations/blob/def89745703a5ccdf4b0a85e04892e06075cb15e/docs/evidence/2026-11-03-hoi4-b037-prompt-followup.json) 已逐字节公开读回。准备状态冻结于真正的派发前时间点；稍后的案例发布不阻塞单路图片生产，根仓库通过此前冻结的 11 份字节提交该历史准备状态，不倒写调用后的日志。

下一组四份真实提示词任务完成后，累计 **97 次本地模型 HTTP 请求、96 份完整候选、1 份截断整次弃用、0 次 HTTP 重试**。owner实际核对四张小卡、放大原始像素和五张大图，排除两张与平民棕毡帽卡服装不同的裸头大图；候选保留软军帽／红带大檐帽、实际胡须和闭领／敞领差异，owner部分采用时再逐项重述原图及圆下巴／短宽领口合同并追加标准透明度约束。[固定提交回执](https://github.com/XenoAmess/local-model-operations/blob/88fcbc89dfc249a897cda5ee00b593c83818df85/docs/evidence/2026-11-03-hoi4-b039-prompt-followup.json) 已公开原始字节读回。这里提交真正派发前冻结的 11 份历史准备字节；后续图片调用与美术结果独立登记，不倒写此前截止。

四份后续裸头闭领提示词完成后，累计 **101 次真实本地模型 HTTP 请求、100 份完整候选、1 份截断整次弃用、0 次 HTTP 重试**。逐源保留短发／秃顶、不同上唇胡、闭领和浅色内领边，以及便笺旁实际露出的星形胸饰／蓝金绳带／彩色章条；owner将第二份候选“不遗漏难辨眼缘”的措辞澄清为未知、不新增显著眼镜，部分采用时补充原图合同和标准圆下巴／短宽领口及透明度要求。[固定提交回执](https://github.com/XenoAmess/local-model-operations/blob/0d2cdd55d4f94e8cc8534e51228e2b372977ea07/docs/evidence/2026-11-03-hoi4-b041-prompt-followup.json) 已公开原始字节读回。准备截止由真正派发前冻结的 11 份字节证明，后续图像执行和审图结果另记。

后续四份不同服装提示词完成后，累计 **105 次真实本地模型 HTTP 请求、104 份完整候选、1 份截断整次弃用、0 次 HTTP 重试**。实际合同区分民装领带、橄榄帽／真实圆框眼镜、深蓝闭领／金领边与便笺旁可见胸饰；第三张大图仅作毛发外观参照，不补入隐藏肩链和勋章。owner部分采用时重述第一张闭口、第三张朝左和胸饰边界，补回第四份候选未明确保留的真实眉毛，再追加标准几何与透明度要求。[固定提交回执](https://github.com/XenoAmess/local-model-operations/blob/daa9c386405c8fea052a4ff29afde579b5217764/docs/evidence/2026-11-03-hoi4-b043-prompt-followup.json) 已公开原始字节读回。派发前 11 份冻结字节与稍后的图像实际执行分开登记。

四份后续提示词任务完成后，累计 **109 次真实本地模型 HTTP 请求、108 份完整候选、1 份截断整次弃用、0 次 HTTP 重试**。owner实际核对不同原尺寸和附件状态：第二张原图53x65、没有便笺，且保留本版绿绶带；共享合同在调用前表达真实便笺存在／缺席，候选保留了这一约束。部分采用时补回第一份缺少的绿圈黑眼、第三份朝左／无眼镜、第四份朝左与真实眉毛，并保留难辨细节边界。[固定提交回执](https://github.com/XenoAmess/local-model-operations/blob/7783e1b7e0602d993bb46751e31114de3509e219/docs/evidence/2026-11-03-hoi4-b045-prompt-followup.json) 已公开原始字节读回。真正派发前的 11 份冻结字节与稍后实际图像执行分开保存；新进度预测另记录连续调度改进后最近窗口的净合格速度，旧整轮预测不倒改。

四份低明度和不同版本提示词完成后，累计 **113 次真实本地模型 HTTP 请求、112 份完整候选、1 份截断整次弃用、0 次 HTTP 重试**。第一张无大图候选，保留黑色发／覆盖轮廓的真实难辨边界、左右不对称暗光与紫黑背板；其余三项比较八张大图，按实际头发、服装和姿态排除不同版本。第二份候选复述了owner输入中非输入大图的比较措辞，最终删除且不归因为模型发明；第四份确认措辞改为直接图像要求，无依据的通用低明度改为实际原图光线。均部分采用、逐图另审。[固定提交回执](https://github.com/XenoAmess/local-model-operations/blob/fe196cafd795b76b7d859690a82a55aec290dcce/docs/evidence/2026-11-03-hoi4-b047-prompt-followup.json) 已公开原始字节读回；派发前的 11 份冻结字节与随后图像执行独立登记。

后续四个真实任务各经共享调用器6次允许尝试后超时，共 **24 次 POST、20 次 HTTP 退避重试、0 份完整候选**。累计实际模型请求增至 **137 次**，完整候选仍为112，另1份历史截断弃用和24份超时尝试；没有把超时当作模型文本采用。owner按已查看原图接管四份提示词，冻结后继续内置图片生产。稍后同配置地址的TCP、GET health/models可达，不证明生成接口恢复或此前服务状态；不切换旧地址、不重投已接管任务。[实际超时与接管回执](https://github.com/XenoAmess/local-model-operations/blob/34ad909f4fac284caf4b78a709f9225ec7c029a0/docs/evidence/2026-11-03-hoi4-b049-timeout-owner-takeover.json) 已公开原始字节读回，真实24次区间、配置/请求SHA与无候选采用边界保留。根仓库提交派发前11份冻结字节；后续图像调用另记。

后续四个全新、尚未完成的来源任务各一次真实本地模型请求均返回 stop/DONE/完整 JSON 候选，没有重投此前 owner 已接管的超时任务。累计 **141 次实际 POST、116 份完整候选、1 份历史截断整次弃用、24 次超时尝试与20次 HTTP 退避重试**。四份部分采用，保留动物角色自然体态、原图红色颈肩布料及无人体服装领口合同，清理候选中的协议尾句并重申真实姿态。此窗口四个生成请求成功只说明该观察窗口可用，不证明服务永久恢复，也不构成实际美术通过。[新任务实际回执](https://github.com/XenoAmess/local-model-operations/blob/c1fd498384af29f7294d5d2c9d2020bd1c62ff70/docs/evidence/2026-11-03-hoi4-b051-prompt-followup.json) 已公开原始字节读回；根仓库保存派发前11份冻结字节，后续图片结果另行验收。

B051 冻结提示词字节保留：熊角色首行末尾的一个空格已实际发送给图片工具，按完整实际 prompt 归档规则原样保存；仅该冻结提示词行的 trailing-whitespace 告警作为精确例外，其余 staged 文件通过 diff 检查，未倒改已调用请求。

后续四个新的真实提示词任务各一次 POST 返回 stop/DONE/完整 JSON，累计 **145 次实际 POST、120 份完整候选、1 份历史截断整次弃用、24 次超时尝试、20 次 HTTP 重试**。四份部分采用，owner重述真实原图方向／头倾、无帽状态及服装，保留第四项确实可见的浅色上唇胡和下巴胡，并与黄色本体圆下巴几何分开；其他图细上唇阴影仍按难辨处理。[实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/862a8f44ad95ee14d899bbf4e277558b9a405221/docs/evidence/2026-11-03-hoi4-b053-prompt-followup.json) 已逐字节公开读回。派发前11份准备字节已冻结保存，后续图片美术资格另审，未以文字 stop 或调用量证明完成。

该组四个新任务各一次真实 POST 返回完整 stop/DONE/JSON，准备截点累计 **149 次实际 POST、124 份完整候选、1 份历史截断整次弃用、24 次超时尝试及20次 HTTP 重试**。四份部分采用；第四份遗漏输入已有的绿圈黑眼由owner补回，大图提醒／被囚替代版说明由owner输入后被模型复述，最终图片词删除这些比较，不把owner材料问题全归模型。实际黑发礼服版、深色闭领及真实上唇胡／光滑下巴约束保留。[实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/418fccb9934a0339eb2ba949a6728b8decd44ce4/docs/evidence/2026-11-03-hoi4-b055-prompt-followup.json) 已逐字节公开读回，完整图片验收另记。此前7574份原始PNG在固定提交00d9525bc的远端原字节核验已完成，后续文件不冒充已读回。

后续四个新的真实提示词任务各一次 POST 返回 stop/DONE/完整 JSON，累计 **153 次实际 POST、128 份完整候选、1 份历史截断整次弃用、24 次超时尝试、20 次 HTTP 重试**。四份部分采用，owner重述真实原图方向／头倾、无帽状态及服装，区分老年灰发敞领军装与年轻闭领版本，保留真实细框眼镜；第四份遗漏输入已有的绿圈黑眼由owner补回，细上唇阴影继续按难辨处理。[实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/7b502dafe7165c01211fbab3020ce443b618f873/docs/evidence/2026-11-03-hoi4-b057-prompt-followup.json) 已逐字节公开读回。派发前11份准备字节已冻结保存，后续图片美术资格另审，未以文字 stop 或调用量证明完成。

该组四个新任务各一次真实POST返回完整stop/DONE/JSON，准备截点累计 **157次实际POST、132份完整候选、1份历史截断整次弃用、24次超时尝试及20次HTTP重试**。四份部分采用，第三项owner曾提供错误的深色领带观察，候选复述该错误；实际原图及原像素放大复核后，在图片首次准备／调用之前更正为红／酒红色，保留原描述、记录SHA、更正时刻与实际HTTP输入／候选原件，不归咎模型独立误识。深色领口、完整胡须与真实眼镜分别保留。[实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/7fab07062c6b30cdd135124fea1809db60f16298/docs/evidence/2026-11-03-hoi4-b059-prompt-followup.json) 已逐字节公开读回。此前7579份原始PNG在固定提交4c1dd961e的远端原字节核验已完成，后续图片另行验收和归档。

后续四个新的真实提示词任务各一次 POST 返回 stop/DONE/完整 JSON，累计 **161 次实际 POST、136 份完整候选、1 份历史截断整次弃用、24 次超时尝试、20 次 HTTP 重试**。四份部分采用，owner重述真实原图方向／头倾、无帽状态及服装，区分实际闭领红滚边、卡其红金领章与敞领金叶海军服、普通西装，颈部金色小饰物仅按原图露出范围保留；细节仍按难辨处理。[实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/6a4b5e5d913fc0dbc6ac91d05e1cf143dce393a1/docs/evidence/2026-11-03-hoi4-b061-prompt-followup.json) 已逐字节公开读回。派发前11份准备字节已冻结保存，后续图片美术资格另审，未以文字 stop 或调用量证明完成。

后续四个新的真实提示词任务各一次 POST 返回 stop/DONE/完整 JSON，累计 **165 次实际 POST、140 份完整候选、1 份历史截断整次弃用、24 次超时尝试、20 次 HTTP 重试**。四份部分采用，owner重述真实原图方向／头倾、无帽状态及服装，第四项原图向左、棕外套／浅衬衫／绿领带，深暗版与灰外套／浅绿衬衫／灰领带版均向右，已在POST前明确并排除作为同版；其他真实银发敞领金叶军装、深发灰领带与金色细框眼镜分别保留。[实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/861909b5d38a67e3a5c4ad5a58d25b77fd1431c5/docs/evidence/2026-11-03-hoi4-b063-prompt-followup.json) 已逐字节公开读回。派发前11份准备字节已冻结保存，后续图片美术资格另审，未以文字 stop 或调用量证明完成。

B65四个新的真实提示词任务各一次POST返回stop/DONE/完整JSON；该批截止累计 **169次实际POST、144份完整候选、1份历史截断整次弃用、24次超时尝试、20次HTTP重试**。四份部分采用，第四份虽已收到具体源特征却只复述通用合同，并漏掉黑色金带大檐帽、红金帽徽、上唇胡与闭领绿金军服；owner在任何图片准备／调用前补齐并删掉协议复述，实际输入和候选原件保留。真实高黄尖帽与黄色本体圆下巴分别约束。 [实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/2505646809ec5aff5cd0bcb8f3a7a508c7a603ff/docs/evidence/2026-11-03-hoi4-b065-prompt-followup.json) 已逐字节公开读回。派发前11份准备字节保持原样；图片美术资格另审。

B67四个新的真实提示词任务各一次POST返回stop/DONE/完整JSON，该批截止累计 **173次实际POST、148份完整候选、1份历史截断整次弃用、24次超时尝试、20次HTTP重试**。第一项原卡向左、银灰斜纹长领带且无便笺，朝右黑／白领结大图在POST前排除，候选保留此边界。第三份完整候选漏掉实际已提供的浅灰敞领西装／浅衬衫／深领带，owner在图片准备和调用前补齐。其他真实闭领橄榄金军服、细框眼镜、灰上唇胡和敞领卡其服分别保留，四份部分采用。 [实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/80efca95072d306d781c022da1264dc38997fb70/docs/evidence/2026-11-04-hoi4-b067-prompt-followup.json) 已逐字节公开读回，11份派发前准备字节原样保留。文字模型不承担像素审图或美术资格。

B69四个新的真实提示词任务各一次POST返回stop/DONE/完整JSON，该批截止累计 **177次实际POST、152份完整候选、1份历史截断整次弃用、24次超时尝试、20次HTTP重试**。第二份漏掉实际已提供的深色金带海军帽，第三份漏掉白色金带海军帽与对应敞领深蓝军服／浅衬衫／深领带，并带出协议和准备器讨论；owner在图片准备和调用前补齐、清除协议复述，原始实际请求和完整候选保留。第一／四份主要灰上唇胡及金色圆细框眼镜、服装保留，四份部分采用。 [实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/70679ccd383f570b8480376c21b871b8822305c1/docs/evidence/2026-11-04-hoi4-b069-prompt-followup.json) 已逐字节公开读回，11份派发前准备字节原样保存。文字模型没有像素审图、美术批准或节省时间结论。

B71四个新的真实提示词任务各一次POST返回stop/DONE/完整JSON，该批截止累计 **181次实际POST、156份完整候选、1份历史截断整次弃用、24次超时尝试、20次HTTP重试**。前三份保留主要闭口微笑／不露齿、棕色军帽及浅卡其敞领军服／浅卡其领带；第四份只复述通用合同，漏掉实际已提供的橄榄军帽、金帽带／浅金帽徽、帽檐下真实眼部阴影和敞领军服／浅卡其衬衫／深领带，并带出协议／准备器说明。owner在图片准备和调用前补齐源特征与光照、删除协议复述，四份部分采用，原始输入和完整候选保留。[实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/2c14d48ff6336ae47f33c351d574f079e9abd9d1/docs/evidence/2026-11-04-hoi4-b071-prompt-followup.json) 已逐字节公开读回，11份派发前准备字节原样保存；文字模型没有像素审图、美术批准或节省时间结论。

B73四个新的真实提示词任务各一次POST返回stop/DONE/完整JSON，该批截止累计 **185次实际POST、160份完整候选、1份历史截断整次弃用、24次超时尝试、20次HTTP重试**。新任务追加逐项明确特征命名要求，不重投已完成题；第二份仍复述通用合同和任务原话，漏掉已提供的卡其折叠船形帽／无帽檐及对应敞领卡其服／浅领带，owner在图片准备和调用前补齐、清除协议复述。第三份保留蓝帽／银色徽饰及蓝军服，但带出协议／准备器说明，owner删去；第一／四份主要银发细金眼镜及短黑上唇胡／深色西装保留。四份部分采用，此有限批次不证明新要求普遍改善。[实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/ae9ec0db83227f14bbc3f7f967f2075b00178d1a/docs/evidence/2026-11-04-hoi4-b073-prompt-followup.json) 已逐字节公开读回，11份派发前准备字节原样保存；文字模型不承担像素审图、美术资格或节省时间结论。

B75四个新的真实提示词任务各一次POST返回stop/DONE/完整JSON，该批截止累计 **189次实际POST、164份完整候选、1份历史截断整次弃用、24次超时尝试、20次HTTP重试**。原卡第三项短黑发／窄深上唇胡且向左，与更高棕色梳发／浓胡须／正面的大图不同，POST前已排除；另分别保留真实银色上唇胡与短下巴须、闭口微笑和闭领金色礼服。本有限批次四份候选保留主要真实帽子／毛发／须型／服装／领带／姿态，没有观察到通用合同单独替代源特征或prompt字段的协议复述。owner部分采用时重述原图及细节限制并补充透明度规则；继续新任务的明确特征要求，但不据此声称受控比较、普遍改善或像素审图。[实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/042a85954cc9f45d0afa83ee0388f59285ad4eb9/docs/evidence/2026-11-04-hoi4-b075-prompt-followup.json) 已逐字节公开读回，11份派发前准备字节原样保存；美术资格另审，未声称节省时间。

B077：四个新任务各一次POST返回完整stop/DONE/JSON。第一项原卡53×65没有便笺，实际同时有蓝色披带和独立棕色斜带；owner输入斜线措辞被候选解释为OR，图片准备前重看原卡明确BOTH，保留实际原词和候选，不归成模型像素误识。其余原图的浅领章绿军服、软橄榄帽／敞领衣和酒红宽领巾分别保留。 该批截止累计 **193次实际POST、168份完整候选、1份历史截断整弃、24次超时尝试、20次HTTP重试**。两个SHA域另验，文字模型没有图像像素、美术批准、服务容量或节省时间结论。[固定实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/e2c7e4135aadb116661d004d26ad35696c1fd455/docs/evidence/2026-11-04-hoi4-b077-prompt-followup.json)已按完整公开原字节核对。准备回执保留实际派发前截点，图片生成／拒绝／美术审图分别记账；本次不以旧准备字节覆盖此前已提交的失败日志。

B079：实际只剩两项可新准备HIGH原图，按真实供应运行2 POST、2完整stop/DONE/JSON，不制造题目凑四路。逐项保留黑色敞领礼服／细小浅领边和口袋折角／难辨深色扣结，以及白色闭合高领礼服／金边／酒红绶带；owner重述原图特征和细节边界后部分采用。 该批截止累计 **195次实际POST、170份完整候选、1份历史截断整弃、24次超时尝试、20次HTTP重试**。两个SHA域另验，文字模型没有图像像素、美术批准、服务容量或节省时间结论。[固定实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/8efa652311980127b57e1849f8649c0c55e04701/docs/evidence/2026-11-04-hoi4-b079-prompt-followup.json)已按完整公开原字节核对。准备回执保留实际派发前截点，图片生成／拒绝／美术审图分别记账；本次不以旧准备字节覆盖此前已提交的失败日志。

B80单个新的LOW来源任务完成1实际POST、1 stop/DONE/完整JSON、0重试，累计 **196次实际POST、171份完整候选、1份历史截断整弃、24次超时尝试、20次HTTP重试**。owner提供实际原卡、原像素放大及匹配分析大图的观察；候选保留真实深色短发／灰鬓和眉毛、干净闭口、深色敞领西装／浅衬衫／红领带和蓝灰摄影底，部分采用时去掉prompt尾端审图协议句和非输入大图饰物讨论。模型未接收像素，不承担美术批准，不据一次调用证明容量或节时。每个LOW窗口只派一张并重新检查HIGH。[固定回执](https://github.com/XenoAmess/local-model-operations/blob/7b4d39f6c6efe37f4505ba6317b330d6f76f33e4/docs/evidence/2026-11-04-hoi4-b080-prompt-followup.json)已完整公开读回。原案例推送遇到远端ref锁竞争后，实际main与远端已同为该rebase后提交，未重放HTTP／案例／提交；并行公开提交保留。派发前5份准备文件按旧截点保存，调用及审图结果另行归档。

B082：一个新任务一次POST完整返回，候选保留真实波浪盘发／眉毛及橄榄棕交叠衣服／金边开放V领，owner部分采用时明确真实衣领V与禁止的长黄色V形颈部分开。后续内置图片实际返回仍因黄色颈部暴露过长被人工拒绝，按精确输出SHA独立返修；没有把文本完整、工具成功或提示词要求当作视觉合格。 该批截止累计 **197次实际POST、172份完整候选、1份历史截断整弃、24次超时尝试、20次HTTP重试**。[固定实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/90511a28096e8b00391581049c2007ddf0ab9356/docs/evidence/2026-11-04-hoi4-b082-prompt-followup.json)已完整公开读回。两个SHA域另验，准备回执保存派发前真实截点；后续图片生成和视觉资格另记，不以文字完整输出证明美术完成、服务容量或节省时间。

B083：一个新任务一次POST完整返回，候选保留稀疏鬓发、实际深色上唇胡与下巴须、闭领橄榄军服／绿金领章及有限棕色斜带。owner补明高发际近秃头顶，分别保留真实尖形胡须与短圆黄色本体，并清除非输入隐藏勋表讨论后部分采用。每个LOW图片窗口只有一张，窗口前重新检查HIGH。 该批截止累计 **198次实际POST、173份完整候选、1份历史截断整弃、24次超时尝试、20次HTTP重试**。[固定实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/7579bfbcc538a24ff30542b18c8df421fbe28c4b/docs/evidence/2026-11-04-hoi4-b083-prompt-followup.json)已完整公开读回。两个SHA域另验，准备回执保存派发前真实截点；后续图片生成和视觉资格另记，不以文字完整输出证明美术完成、服务容量或节省时间。

B085：一个新任务一次POST完整返回，候选保留白披巾／深金额箍、浓密全下颌胡须及敞领橄榄军服／浅衬衫／深领带，较年轻SYR同名大图已排除。实际内置图232返回后，owner放大原始像素确认额箍为三层，先前提供DOUBLE是owner观察错误，候选忠实复述。原观察、实际HTTP／候选及图片词不倒改；同一共享回执追加明确后到更正，返回两层版本拒绝资格，另排SHA绑定返修，不把这归为模型像素错误。 该批截止累计 **199次实际POST、174份完整候选、1份历史截断整弃、24次超时尝试、20次HTTP重试**。[固定实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/a9c5ee101ebcb36d0883770e4755a9f355c097f5/docs/evidence/2026-11-04-hoi4-b085-prompt-followup.json)已完整公开读回。两个SHA域另验，准备回执保存派发前真实截点；后续图片生成和视觉资格另记，不以文字完整输出证明美术完成、服务容量或节省时间。

B086：一个新任务一次POST完整返回，候选保留白色海军帽／金饰／深帽檐与真实眉眼阴影、深色上唇胡／全下颌胡须和敞领深蓝军服／浅衬衫／深领带。owner部分采用时重述原卡、露发边界、短宽领口及有限可见饰物；年轻同名大图在POST前排除。每个LOW图片窗口一张，调用前重新检查HIGH；微小徽纹未冒充精确还原。 该批截止累计 **200次实际POST、175份完整候选、1份历史截断整弃、24次超时尝试、20次HTTP重试**。[固定实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/17fcd19135e3e9bede9ed5d65896ad73fd3d59b2/docs/evidence/2026-11-04-hoi4-b086-prompt-followup.json)已完整公开读回。两个SHA域另验，准备回执保存派发前真实截点；后续图片生成和视觉资格另记，不以文字完整输出证明美术完成、服务容量或节省时间。

B087：一个新任务一次POST完整返回，候选保留原卡向左、窄深色上唇胡／很短下颌胡茬、白海军帽／有限金饰和敞领深蓝军服／浅尖衬衫领／深领带。三张分析候选的白胡须、缠头巾长须或相反朝向在POST前排除；部分限制位于候选limits，owner以原卡重述把额外帽檐金叶／隐藏勋章限制写入实际图片词。 该批截止累计 **201次实际POST、176份完整候选、1份历史截断整弃、24次超时尝试、20次HTTP重试**。[固定实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/26bf4d43bf59c64123ee06a24907dd3c2f342682/docs/evidence/2026-11-04-hoi4-b087-prompt-followup.json)已完整公开读回。两个SHA域另验，准备回执保存派发前真实截点；后续图片生成和视觉资格另记，不以文字完整输出证明美术完成、服务容量或节省时间。

B089：一个新任务一次POST完整返回，候选保留银灰发／真实眉毛、小银色上唇胡／干净下巴和敞领平民西装／浅衬衫／红领带，保留原卡朝向、裁切和遮挡。owner部分采用时删除其他军服／年轻军帽版本比较，换为直接视觉限制，不添加便笺后隐藏领针；不同SHA的服装版本继续独立处理。 该批截止累计 **202次实际POST、177份完整候选、1份历史截断整弃、24次超时尝试、20次HTTP重试**。[固定实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/34f229e26502bce77317b9a86619fa0cf86824d0/docs/evidence/2026-11-04-hoi4-b089-prompt-followup.json)已完整公开读回。两个SHA域另验，准备回执保存派发前真实截点；后续图片生成和视觉资格另记，不以文字完整输出证明美术完成、服务容量或节省时间。

B090：一个新任务一次POST完整返回，候选保留实际蓝色短领结及左右布翼、下方浅色衬衫前襟，未替换成红色或浅色长领带。银灰发／真实眉毛、小银色上唇胡／干净下巴、敞领深色外衣及原卡姿态均保留，owner重述具体细节和短宽领口／透明度后部分采用；相同脸型不同服装的原始SHA仍独立生成。 该批截止累计 **203次实际POST、178份完整候选、1份历史截断整弃、24次超时尝试、20次HTTP重试**。[固定实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/ba9b42f90932cfc34c2ad49c478bd3fff29ad1a6/docs/evidence/2026-11-04-hoi4-b090-prompt-followup.json)已完整公开读回。两个SHA域另验，准备回执保存派发前真实截点；后续图片生成和视觉资格另记，不以文字完整输出证明美术完成、服务容量或节省时间。

B092：一个新任务一次POST完整返回，但prompt主要复述通用合同、任务和协议／准备器说明，具体发须／橄榄绿敞领衣／浅衬衫／深长领带仍写成Explicitly name草拟命令。owner清除所有任务／协议复述和含糊条件须句，在任何图片准备／派发前补齐真实银灰发／眉毛／上唇胡／干净下巴／闭口／具体衣服与裁切后部分采用。完整输入和原始候选保留，此新反例不支持明确命名要求已普遍解决问题，也未重投旧绿任务。 该批截止累计 **204次实际POST、179份完整候选、1份历史截断整弃、24次超时尝试、20次HTTP重试**。[固定实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/b8936fc9758672315fa795c2c0ce5dff0a25a551/docs/evidence/2026-11-04-hoi4-b092-prompt-followup.json)已完整公开读回。两个SHA域另验，准备回执保存派发前真实截点；后续图片生成和视觉资格另记，不以文字完整输出证明美术完成、服务容量或节省时间。

B093：一张新LOW真实任务采用纯视觉SOURCE与已完成祈使句要求；本候选未在prompt回显协议，通用背景简称由owner在图片准备前改为实际蓝灰，原始输入/响应保留。后续原图240因黄色下颌拉长收尖被人工拒绝，返修242另行验收，不追认初次图合格。 该批截止累计 **205次实际POST、180份完整候选、1份历史截断整弃、24次超时尝试、20次HTTP重试**。[固定实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/c428f54606130f982f3b73c3d5c905f1beadbebb/docs/evidence/2026-11-04-hoi4-b093-prompt-followup.json)已完整公开读回。两个SHA域另验，准备回执保存派发前真实截点；后续图片生成和视觉资格另记，不以文字完整输出证明美术完成、服务容量或节省时间。

B094：一张新LOW来源为开襟西装、浅衬衫与深色长领带；owner旧模板夹带细领结纹样句，候选照抄，准备图片前已删除并重述真实长领带。归类为owner输入污染，非模型看图失败；原始HTTP和完整候选保留。 该批截止累计 **206次实际POST、181份完整候选、1份历史截断整弃、24次超时尝试、20次HTTP重试**。[固定实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/7028ebc5765b90effd728b57e1e62d8abe93db91/docs/evidence/2026-11-04-hoi4-b094-prompt-followup.json)已完整公开读回。两个SHA域另验，准备回执保存派发前真实截点；后续图片生成和视觉资格另记，不以文字完整输出证明美术完成、服务容量或节省时间。

B095：一张新LOW用逐源配置准备纯视觉SOURCE与通用TASK，避免沿用其他头像的服饰任务字句。本候选保留隆起黑发/真实眉、闭合橄榄服、浅灰蓝领缘、橙金小领章/中央金扣及近正面略朝左；反向黑领大图排除，owner补齐短圆U下颌与极短宽领口衔接。 该批截止累计 **207次实际POST、182份完整候选、1份历史截断整弃、24次超时尝试、20次HTTP重试**。[固定实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/aa8ea63f04658896aa5a1d0cd3daa6a8b7822902/docs/evidence/2026-11-04-hoi4-b095-prompt-followup.json)已完整公开读回。两个SHA域另验，准备回执保存派发前真实截点；后续图片生成和视觉资格另记，不以文字完整输出证明美术完成、服务容量或节省时间。

B097：一张新LOW原图的暗帽与浅棕纹样闭合领口不匹配22张实际查看的大图候选，全部排除后按主小图可见特征起草。候选保留严肃微张口、真实眉与外露发、近正面略朝左及暗灰卡底；owner补齐模糊刻纹限制、短圆U头型和极短宽领口衔接。 该批截止累计 **208次实际POST、183份完整候选、1份历史截断整弃、24次超时尝试、20次HTTP重试**。[固定实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/3882d3a3bd212be8d16ab528cc875f0e1bd1e9ec/docs/evidence/2026-11-04-hoi4-b097-prompt-followup.json)已完整公开读回。两个SHA域另验，准备回执保存派发前真实截点；后续图片生成和视觉资格另记，不以文字完整输出证明美术完成、服务容量或节省时间。

B098：一张新LOW候选prompt保留深橄榄大檐帽/有限金棕帽带小徽、黑色及颏短发、开襟橄榄服/浅灰蓝衬衫/深长领带。limits字段回显任务字句，未采用或发给图片工具；实际完整JSON保留，prompt与limits采用范围分别记录。 该批截止累计 **209次实际POST、184份完整候选、1份历史截断整弃、24次超时尝试、20次HTTP重试**。[固定实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/cdb1d54d4ba936996895bc961700585741436253/docs/evidence/2026-11-04-hoi4-b098-prompt-followup.json)已完整公开读回。两个SHA域另验，准备回执保存派发前真实截点；后续图片生成和视觉资格另记，不以文字完整输出证明美术完成、服务容量或节省时间。

B099：一张新LOW完整输入明确普通卡其软军帽且不要金色帽徽/帽带，候选却添加该细节；owner在图片准备前纠正精确字句并重述禁项，不重投文字请求。此为源齐情况下的否定语义错误，原始HTTP/候选保留；主图朝左、短黑发、折领浅开口与暗内层等继续保留。 该批截止累计 **210次实际POST、185份完整候选、1份历史截断整弃、24次超时尝试、20次HTTP重试**。[固定实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/4b10877832f52c1349c3b64bd746735c53b1395a/docs/evidence/2026-11-04-hoi4-b099-prompt-followup.json)已完整公开读回。两个SHA域另验，准备回执保存派发前真实截点；后续图片生成和视觉资格另记，不以文字完整输出证明美术完成、服务容量或节省时间。

B100：一张新LOW候选prompt保留实际深橄榄大檐帽/小徽、棕色短刘海、开襟暗橄榄服/卡其尖衬衫领/深长领带及朝左视角。未采用limits任务回显，owner重述靠近嘴部的短圆U头型与宽领口接触；完整HTTP/JSON保留，图片另行验收。 该批截止累计 **211次实际POST、186份完整候选、1份历史截断整弃、24次超时尝试、20次HTTP重试**。[固定实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/2a60b3bd09f8c10371d8291b056eef19b6bf5dcc/docs/evidence/2026-11-04-hoi4-b100-prompt-followup.json)已完整公开读回。两个SHA域另验，准备回执保存派发前真实截点；后续图片生成和视觉资格另记，不以文字完整输出证明美术完成、服务容量或节省时间。

B102：一张新LOW候选prompt保留浅卡其帽带/帽檐、小浅金徽、棕色短波发、实际浅金/灰窄领口区域、严肃闭口和轻朝左姿态。细小服饰结构不确定处保持克制，不凭空补西式领带/勋章；limits任务回显未采用，owner重述短圆U下缘与极短宽衔接。 该批截止累计 **212次实际POST、187份完整候选、1份历史截断整弃、24次超时尝试、20次HTTP重试**。[固定实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/2d94bf6e2b19c303cab0c51cb083ee0a9d257065/docs/evidence/2026-11-04-hoi4-b102-prompt-followup.json)已完整公开读回。两个SHA域另验，准备回执保存派发前真实截点；后续图片生成和视觉资格另记，不以文字完整输出证明美术完成、服务容量或节省时间。

B103：一张新LOW候选保留短紧卷后退黑发、真实眉、开襟深蓝服/浅衬衫/红长领带及小金色左领标记。大图基本服饰匹配，浅米背景与更细徽记不继承，主小图蓝灰卡底/近正面姿态仍为准；未采用limits任务回显，owner补短圆U头型和宽衬衫领衔接。 该批截止累计 **213次实际POST、188份完整候选、1份历史截断整弃、24次超时尝试、20次HTTP重试**。[固定实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/bb6139466a690bb55cd36035789a70b374c8a57d/docs/evidence/2026-11-04-hoi4-b103-prompt-followup.json)已完整公开读回。两个SHA域另验。准备回执保存派发前真实截点；后续图片生成和视觉资格另记，不以文字完整输出证明美术完成、服务容量或节省时间。

B104：一张新LOW候选保留短密深发/真实眉、完整真实深色胡须、开襟深蓝服/浅衬衫/红长领带与微小金色左领标记。owner重述胡须毛发边缘与底下黄色圆头分开，避免黄色V下颌；微小唇部/标记克制，limits未采用。 该批截止累计 **214次实际POST、189份完整候选、1份历史截断整弃、24次超时尝试、20次HTTP重试**。[固定实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/ab950c2be5a3fc11e6284e58b8ef31ea33706f4e/docs/evidence/2026-11-04-hoi4-b104-prompt-followup.json)已完整公开读回。两个SHA域另验。准备回执保存派发前真实截点；后续图片生成和视觉资格另记，不以文字完整输出证明美术完成、服务容量或节省时间。

B105：一张新LOW文字任务在1700输出token处length截断，整份弃用，未重投/续接。owner按调用前已有的逐源观察与纯视觉合同独立准备提示词，保留细金矩形眼镜、主图朝左、红长领带与蓝灰卡底，反向大图排除；未将owner接管写成模型采用。 该批截止累计 **215次实际POST、189份完整候选、2份历史截断整弃、24次超时尝试、20次HTTP重试**。[固定实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/3ed4e87871ad28294fb1b0dc19403a6e2d3e5e9b/docs/evidence/2026-11-04-hoi4-b105-prompt-followup.json)已完整公开读回。本批HTTP200/SSE_DONE但length截断，0完整候选，残片未读取/拼接/解析/采用；两个SHA域只核对原始输入合同。准备回执保存派发前真实截点；后续图片生成和视觉资格另记，不以文字完整输出证明美术完成、服务容量或节省时间。

B106：一张新LOW实际候选保留短后梳深发/灰鬓、真实眉、浓上唇胡/干净下巴、开襟深蓝服/浅衬衫/红长领带和小金左领标记，反向较秃大图排除。本候选满足新任务limits最多20词要求，不据单例解释既有截断或宣称普遍改善；后续图片将领标放错侧，另行拒绝和返修，不归因文字合同。 该批截止累计 **216次实际POST、190份完整候选、2份历史截断整弃、24次超时尝试、20次HTTP重试**。[固定实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/b67fa5194d590b8fda344710ca5a8773348ff620/docs/evidence/2026-11-04-hoi4-b106-prompt-followup.json)已完整公开读回。两个SHA域另验。准备回执保存派发前真实截点；后续图片生成和视觉资格另记，不以文字完整输出证明美术完成、服务容量或节省时间。

B107：一张新LOW保留稀疏灰发、有限灰唇颏毛发、开襟深蓝服/浅衬衫/蓝短领结。但事后查明：SOURCE明确绿环黑眼，完整候选与实际图片prompt漏掉该要素，owner也未补回；图片254呈真人脸涂黄，已拒绝。源齐遗漏和owner接管边界已公开留证，旧实际字节保留，仅新任务与SHA返修重述真实角色结构；未证明措辞为唯一原因。 该批截止累计 **217次实际POST、191份完整候选、2份历史截断整弃、24次超时尝试、20次HTTP重试**。[固定实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/5b6c9b09582c7a79991320f6e3297a19d07b94f2/docs/evidence/2026-11-04-hoi4-b107-prompt-followup.json)已完整公开读回。两个SHA域另验。准备回执保存派发前真实截点；后续图片生成和视觉资格另记，不以文字完整输出证明美术完成、服务容量或节省时间。

B109：一张新LOW在新SOURCE、候选及最终owner准备中明确大绿环黑眼、小灰嘴和平滑奶龙结构，同时保留高退发侧发、完整深胡须、开襟深蓝服/浅衬衫/蓝短领结与主图角度/蓝灰卡底。来源接触页先于POST，直接native/nearest复核在POST后且图片准备前完成。非旧绿重投或措辞单因素实验，美术资格另记。 该批截止累计 **218次实际POST、192份完整候选、2份历史截断整弃、24次超时尝试、20次HTTP重试**。[固定实际调用与采用回执](https://github.com/XenoAmess/local-model-operations/blob/9aca0cc408e5bda6eb2abeff7d4468e5f2c40be7/docs/evidence/2026-11-04-hoi4-b109-prompt-followup.json)已完整公开读回。两个SHA域另验。准备回执保存派发前真实截点；后续图片生成和视觉资格另记，不以文字完整输出证明美术完成、服务容量或节省时间。
