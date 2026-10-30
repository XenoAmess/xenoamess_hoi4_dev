# 2026-10-30 实机头像覆盖核查（本地工作记录，未发布）

- 机器：`bf-202609141645-5434332d4d`；HOI4：Operation Postern 1.19.3.0.c01a (5632) (S)；Steam 离线；所有游戏/启动器观察采用原始桌面截图、OCR 与键鼠。
- 旧测试包 `dist/hd-masking-sample-set-20261019-q` 只有 Roosevelt、Patton、Halsey 三个来源。2026-10-30T05:14:52.413377+00:00 的原始选国画面 `runtime/release-20261030/before-exit.png`（SHA-256 `1e59b62bdb81d927bf7638335f4494ceb3a145b1c5c53ca53a997dd547c72346`）确实只有美国卡被替换。其余选国卡保留真人是错误地使用局部测试包造成的，不能作为全量模组验收图。
- 本地重新构建并部署的 `dist/release-20261030-country-qa` 包含 11 个高清来源与 12 个有实际原版定义依据的适配绑定，仍明确标为 `INCOMPLETE PREVIEW`。启动器 2026-10-30T05:23:31.767097+00:00 原始截图 `runtime/release-20261030/playset-new.png`（SHA-256 `541a766fdaaf63da0fdb31c8c5c7ed6da17ec05e500575040f33df2f56c76180`）显示测试播放集启用此包。
- 2026-10-30T05:50:26.213262+00:00 原始选国画面 `runtime/release-20261030/country-cards-new.png`（SHA-256 `d8af4a5b8f4c147e838e4a9abf8ed31e23c1a6f3469fb5cf85b3616d91942449`）可见七张主卡都有奶龙图像；后续逐人对照发现德国位置串用了法国/美国图。**“出现奶龙”不等于人物身份正确，这张图没有通过验收。**
- 2026-10-30T05:57:09.293488+00:00 的英国开局设置画面 `runtime/release-20261030/uk-setup.png`（SHA-256 `70d730a9903deb08cc79df1a048eb852b474352145eff208e73e30fa4786cbf7`）及 2026-10-30T06:07:10.524774+00:00 的英国政治界面 `runtime/release-20261030/uk-politics.png`（SHA-256 `7590dd109a0a87bda55c3a414fbbdaf6ccc5513ed653be75b87d09a7eea585a4`）显示 Stanley Baldwin 大头像正常，但“国家精神”栏仍有真人小像。
- 点击该小像后的 2026-10-30T06:15:14.198998+00:00 原始截图 `runtime/release-20261030/uk-politics-small-icon-after.png`（SHA-256 `4479d5163f8a304ee7b4808b7b6180d314240a98ae05b446e7ea57de8341e5f5`）OCR 读回 `King George V`。本机原版 `common/ideas/britain.txt` 使用 `george_v`，`interface/ideas.gfx` 的 `GFX_idea_george_v` 绑定 `gfx/interface/ideas/idea_george_v.dds`。当前 `data/catalog.json` 没有该纹理路径。因此它不仅没进入 11 图样本，也没进入已有全量人物清单；需要补充有图像证据的清单规则、单独生成审图，并验证该国家精神的实际尺寸和工具提示。

后续根因核查：V2 与将白色布局载体隔离的 V3 出现相同德国串图，隔离载体不是已验证的修复。V3 的新鲜游戏 `error.log` 明确记录 `Failed to load texture larger than MAX_TEXTURE_SIZE: gfx/leaders/GER/portrait_GER_adolf_hitler.dds`。对应高清母版为 1776×2368；原始 PNG 与正确人物绑定无误。游戏内部为何回显其他已加载纹理仍属推断，未使用内存或调试接口。当前已通过素材清点发现 71 个来源为同尺寸，需受控实机验证尺寸例外后修复，详见 `data/texture-load-risk-census-20261030.json`。

King George V 已补录、单独生成并通过原图/完整母版/透明度/领口审查；新生成图只证明美术通过。已实际审图确认的国家精神卡及其 DLC 覆盖共 328 个资源记录加入清单，另有普通符号尺寸及其他 DLC 路径尚待视觉排查，不能声称这已穷尽所有漏项。目录现含 5712 个资源、5485 个不同来源；旧的全量分母已经不适用。

当前结论：**串图修复及全人物覆盖仍未通过实机验收**。上述原始截图不得作为正式发布验收图。继续核查人物身份、加载错误、国家精神图标、顾问、军官与其他显示入口。此记录不代表已执行 Git、Steam 上传或公开发布。
