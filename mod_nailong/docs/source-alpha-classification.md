# 原背景与调用透明度分类

本机 `bf-202609141645-5434332d4d` 于2026-10-23人工对照原图、实际高清返回、白/青背景和alpha面板，确认部分完整矩形原图的alpha最小值只有240、242或246，仍有完整绘制背景。旧249阈值将这些新请求设为 `transparent_background=true`，与保留整幅背景的返修要求冲突。观察值和实际发送参数见[诊断记录](../data/resumed-20261023-alpha-dispatch-inspection.json)。这不证明所有低alpha来源都是完整画布，也不单独证明服务生成缺陷的全部原因。

`generation_requests.prepare` 现在可通过明确的 `opaque_canvas_reason` 为已实际审查的单项来源记录整幅背景分类，发送不透明背景参数并持久化完整提示词、理由和原alpha范围。该入口拒绝空理由以及存在全透明像素的来源，不修改原版或返回PNG字节。未指定理由时沿用既有分类；不能依据目录、姓名或任意新阈值批量认定。`verify_source_alpha_policy.py` 覆盖默认边界、诊断值、理由门禁、真实透明边缘保护和输入不变性。

这只适用于新准备的合规美术请求。被服务拒绝的冻结请求必须继续保持原prompt、参数和输入字节；不得通过本入口改写或绕过冷却。尚未发送的独立美术返修如需更正参数，先逐项证明没有dispatch，再保留旧请求并登记取消，随后新建attempt。见[本轮未发送请求调整](../data/resumed-20261023-unsubmitted-canvas-job-reconciliation.json)。

返回后仍须人工检查整幅背景、衣物及人物内部是否实际不透明，并复查原图特征与领口；参数正确、静态数值或构建通过均不等于审图或HOI4实机通过。

本轮普通美术返修还发现：只读取最近一次请求可能丢失更早已逐项记录的完整画布理由。后续准备器可沿该来源的历史 attempt 查找已有 `source-manually-verified-opaque-canvas-v1` 记录，但必须核对其原图转换 PNG SHA 与当前原图完全一致，保留原理由，并在新准备回执登记继承自哪一次 attempt。这只影响实际返回 PNG 之后的新美术返修；不改写历史实际参数、被拒请求或冷却重试。漏传理由产生的透明返回仍保留原始字节并撤出合格集，见[保留原特征批次审图](../data/resumed-20261023-original-features7-review.json)与[表情批次审图](../data/resumed-20261023-expression-badges8-review.json)。
