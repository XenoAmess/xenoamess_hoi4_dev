# XenoAmess 的 Hearts of Iron IV 模组开发

公开仓库：<https://github.com/XenoAmess/xenoamess_hoi4_dev>。

面向 HOI4 的多模组工作区。每个独立产品放在自己的 `mod_<name>/` 下，独立保存素材、源码、清单、工具、文档和构建入口。游戏、Steam 和启动器的实际操作采用**截图/OCR＋键鼠**；无 MCP、游戏注入或后端服务。

```text
xenoamess_hoi4_dev/
├── AGENTS.md
├── tools/                     # 共享 Python：机器身份、桌面 OCR/键鼠等
├── docs/                      # 共享知识与存储规则
├── workshop/products.json     # 产品身份；未发布 ID 保持 null
└── mod_nailong/
    ├── AGENTS.md
    ├── README.md
    ├── assets/                # 用户参考图、提示词、生成后规范尺寸 PNG
    ├── data/                  # 原图清点、生成来源与审图记录
    ├── mod/                   # 游戏 payload 源（生成 DDS 不入库）
    ├── tools/                 # 清点、续跑、导入、构建
    └── docs/                  # 本产品验收、边界和进度
```

首个产品是 [奶蛙世界](mod_nailong/README.md)：逐原头像融合用户提供的奶蛙角色，保留衣物、神态和动作。全量生产尚在进行，**不是已完成的全人物替换包**；精确进度由 `portraits.py coverage` 读回。

全量目标为 5,238 张不同原图，其中 4,535 张高优先级先制作；扫描器路径更正找回的 95 张小头像见[路径更正](mod_nailong/docs/catalog-path-normalization.md)，另有 14 张未绑定角色的小头像见[独立卡片补漏](mod_nailong/docs/catalog-unbound-portrait-cards.md)。当前数量与快照时间见[生产进度](mod_nailong/data/progress.json)。用户已采用保留原人物发型、胡子等特征的版本，并追加粗脖子与衣领的协调检查。原 23 张不同原图/26 个资源的 A/B 对照已完成，后续按同一规则持续生产。

领口修正版已在实际选国页面和罗斯福信息卡显示，构建、机器和验收范围见[preview-007 实机回执](mod_nailong/docs/collar-preview-007-runtime.json)；其他新图仍需各自审查，不据局部画面追认全量通过。内置图片工具的 1/4/8 路实测与吞吐边界见[并发记录](mod_nailong/docs/builtin-image-concurrency.md)，目前按用户决定单路连续制作。

![领口修正版的局部实机画面](mod_nailong/docs/media/2026-10-17-collar-preview-007.png)

```text
python -m pip install -r requirements.txt
set HOI4_GAME_ROOT=<实际 HOI4 安装目录>
python mod_nailong/tools/catalog.py scan
python mod_nailong/tools/catalog.py prepare --limit 16
python mod_nailong/tools/portraits.py coverage
python mod_nailong/tools/build_release.py --preview --check
python mod_nailong/tools/build_release.py --preview --output dist/naiwa-preview-001
```

`set` 是 Windows cmd 的环境变量命令。也可对 `catalog.py scan` 传 `--game-root`。开发构建无需启动 Steam，也不要求 Steam 在线。图像生成使用内置 imagegen skill，不要求 API key；仓库 Python 工具不会偷偷换用付费 API。

永久协作规则见 [AGENTS.md](AGENTS.md)：每次任务默认提交并推送；Steam 仅在下载/上传等必要阶段在线，完成或中止后立即恢复离线。GitHub 推送和图片生成无需改变 Steam 状态。
