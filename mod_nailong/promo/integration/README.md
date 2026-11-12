# 钢奶龙心宣传片工具链接入

此包为本项目注册 `hoi4-ocr-capture` adapter、`gangnailongxin-75s` preset 与 `nailong_promo:compose`，复用 XAR Promo Toolchain 0.3.0 的留存、时间线、音轨、字幕、编码编排与审阅接口。它不控制游戏或 Steam。

当前已验证真实六段素材的索引读取、七类不一致输入的拒绝、八种布局样张，以及缺少拍摄素材时 CLI `plan` 返回 RED 且不创建 workdir。另已用核心 `plan_render` 渲染并探测一个五秒标题组件：1920×1080、30 fps／150 帧、48 kHz 双声道，含真实准备的旁白、字幕与临时配乐。**尚未完成全片的成功 plan、build 或人工审阅**；顾问录像与干净的头像揭示镜头仍待补拍。

在已安装核心工具链的隔离环境中安装本包：

```text
python -m pip install -e mod_nailong/promo/integration
```

制作 owner 完成补拍及原片核对后，准备本机 `gangnailongxin-promo-production-inputs-v1` JSON，并通过 `NAILONG_PROMO_INPUTS` 环境变量指定它。该文件位于已忽略的工作包中，拥有：

- `project_root`、`capture_complete`、`remaining_capture` 与精确的 `casting_policy`；缺少镜头时 `capture_complete` 必须为 false。
- `capture_index`：项目根内的已核字节 capture index；各原片的 span 名和时间边界来自实际 generic capture receipt。
- `style`、`shot_plan`、`arts`、`narration`、`score`：各输入的 `path/bytes/sha256` 绑定；原画仍留在原处。
- `narration_texts`、`subtitle_cues`：当前旁白原文、实际配音得到的全片时间和字幕文字；`shots`：按 S01–S08 分组的 phase 配方。

每个 phase 拥有正数 `seconds`、布局 `layout` 与可选 `art` 人物 ID。实录 phase 另外指定 `clip_id`、`span_id`、`start_seconds` 与可选 `[left,top,width,height]` 原始像素裁切；时间必须位于已选 span 内。S05 可用三个各四秒的 phase，S07 可分两段各六秒。标题与片尾使用明确标注的美术插入。

`capture_complete` 由拍摄 owner 在实际核对画面后填写；索引字节验证不判断人物身份或画面含义。实录章节缺少 source，或保留 `missing_capture_role` 时，即使单独把该标志改成 true，也会被拒绝。初次绑定错误的模型候选有三类反例，owner 修正后七类负例均拒绝；原始候选与实际采用范围单独留存。

完成输入后，沿核心 CLI 使用新的 workdir：

```text
xar-promo plan <config-or-run> --workdir <new-plan-dir> --composer nailong_promo:compose --validate-only
xar-promo build <new-run-manifest> --workdir <new-build-dir> --composer nailong_promo:compose
```

`plan` 为只读；布局、编码、FFmpeg probe 和音轨制作均不得在该阶段执行。正式 build 使用项目视觉 resolver 构图，再由核心 `plan_render` / `plan_concat`、字幕与音轨接口完成合成和保留命令审计。当前时间线通过核心 `plan_storyboard` 读取已准备 WAV 的实际长度作为草拟估计值；没有把它标成未实现的旁白 resolver。

成功 build 只生成审阅候选。完整观看、技术与语义核对、精确字节 probe、具名 signoff 和离线 export 仍按工具链流程执行；未获视频发布指示时不上传。
