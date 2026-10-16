# 奶蛙世界 / Naiwa World

把 HOI4 人物本体替换为用户参考图中的奶龙，保留原服装、帽子、配饰、姿态、表情和取景，**同时保留原人物可见的发型、胡子、眉毛等附属特征**。用户于 2026-10-16 决定全部旧图和后续图片均采用此版本。目录 `mod_nailong` 遵照用户指定命名，角色外观以实际 ZIP 图片为准。

当前为 **0.1.0-dev 开发预览**，尚未发布到 Steam Workshop。目标包括原版与已安装 DLC 的领袖、将领、顾问大小头像、通用人物、间谍、科学家与王牌飞行员；其他 Workshop 模组与未来游戏更新需重新清点。

![毛发特征对照：每组左为旧版，右为已采用新版](docs/media/hair-features-comparison.png)

![实际游戏中的奶蛙版罗斯福和斯大林](docs/media/2026-10-16-usa-in-game.png)

上图来自 `machine_id: bf-202609141645-5434332d4d`，2026-10-16 02:38 UTC，HOI4 1.19.3.0，首次四头像开发包，使用此前不保留毛发的 A 版。完整来源、原图 SHA 和适用范围见[会话回执](docs/session-2026-10-16.json)。这张历史图不能证明新版或其他图片实机通过。

当前采用的毛发特征规则与迁移说明见[毛发版本生产记录](docs/hair-features-production.md)。原 26 个资源实例的对照实验在 [experiments/hair-features-v1/](experiments/hair-features-v1/)，冻结了 23 张不同原图对应的旧图和完整旧 prompt。所有新生成及返修在请求前保存完整实际 prompt，成功、失败和被弃用的尝试均留记录。

## 生产流程

1. `python mod_nailong/tools/catalog.py scan`：从实际安装读取原版/DLC 文件、角色定义和 sprite 引用，记录源 SHA 与机器/版本。不会复制完整游戏资产到仓库。
2. `python mod_nailong/tools/catalog.py prepare --limit 16`：准备尚未完成的原图与输入 contact sheet；完全相同的原始字节共用生成，其他变体独立生成。
3. 用 imagegen skill 检查原图，逐张引用原图与 `assets/reference/naiwa.png`，保留原人物毛发特征。请求前保存完整实际 prompt；基础提示词在 [portrait-prompt.txt](assets/portrait-prompt.txt)，实际调用词另行逐次落盘。不可用程序贴头、统一通用头像或滤镜冒充。
4. `python mod_nailong/tools/portraits.py import --key <原图SHA256> --image <生成文件.png> --prompt-file <实际提示词.txt>`：只做规范尺寸转换，保存图片来源与 SHA；原始大图仍保留在本机外置生成目录。
5. `python mod_nailong/tools/portraits.py sheet`：审查输出，对照原图确认服装、神态和动作。审图后运行 `approve pending-sheet`；未看图不得批准。
6. `python mod_nailong/tools/portraits.py coverage`：读回生成/审图数量。
7. `python mod_nailong/tools/build_release.py --preview --check`：双构建，逐文件核对 ZIP、DDS 解码与原尺寸。`--preview --output <全新目录>` 生成显式不完整预览包；正式构建不带 `--preview`，会在覆盖不足或缺失引用未解决时拒绝。

构建按原版虚拟纹理路径覆盖，只包含已生成并审查的图片和 descriptor。不覆盖人物属性、国家历史或全局目录，不使用 `replace_path`。头像原尺寸保留，小图透明度经 DDS RGBA 保存。

共享虚拟路径的多个 DLC 变体全部保留在库存；当前 builder 默认按 DLC 数字 ID 选择本机全部已安装内容的候选，`--packages` 可冻结指定 DLC 列表（空列表表示仅原版）。这一顺序仍须对照目标启用 DLC 的实机验证，不能据静态规则声称任意 DLC 组合已通过。

## 当前边界

- 完整库存含数千张原图，逐张生成尚未完成；没有用通用奶蛙图填满空位。
- 当前数量以[进度快照](data/progress.json)为准；`textures_reviewed` 仅计符合当前毛发规则且已审图的资源。旧 23 张/26 资源统计是 A 版历史基线，不能抵扣新版迁移；全量目标仍为 5,129 张不同原图。棺木状态标记与扑克牌占位图经原图审查确认不含人物，已在 catalog 中显式注明排除。
- 原版角色定义中存在本机未找到 sprite 定义的引用，见 `data/catalog.json` 的 `unresolved_references`；仍需分辨上游缺口、条件加载和扫描范围。不得隐藏它们以形成 100% 完成结论。
- [原版引用分析](data/baseline-reference-analysis.json)已将 899 次缺失分为 852 个不同值：694 个名字在已扫描 sprite/纹理集合中未定义，158 个 sprite 的目标纹理在已扫描安装集合中未找到。原定义 SHA 已固定；此结果不证明引擎的运行时 fallback，也没有擅改原版人物定义。
- 图像生成服务已拒绝一张德国历史领袖原图，保留 [真实失败记录](data/generation-failures.json)。没有把拒绝项写成成功或使用替代通道绕过拒绝。
- `prepare` 自动跳过该被拒主题的变体，继续其他素材；跳过项仍计入未完成分母。
- UI 奶蛙化为低优先级奖励，尚未交付。
- 提示词与生成审图记录见 [generated.json](data/generated.json)；构建通过不等于游戏实机通过。

机器与首批来源见 [开发记录](docs/development-2026-10-16.md)。
