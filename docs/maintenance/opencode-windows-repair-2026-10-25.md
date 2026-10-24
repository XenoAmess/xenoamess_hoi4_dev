# OpenCode Windows 启动修复（2026-10-25）

本机实证：`bf-202609141645-5434332d4d`；观察 UTC `2026-10-24T16:15:25.244534+00:00`；
完成 UTC `2026-10-24T16:18:33.347463+00:00`。适用范围仅为本机 pnpm 全局安装的
`opencode-ai@1.19.4`，不代表其他机器或版本已验证。

## 原因

系统为 Windows 10 x64，版本 `10.0.19045`。报错路径中的 `bin/opencode.exe`
只有 479 字节，实际内容是提示 postinstall 未运行的 shell 文本，开头为
`echo "Error: opencode-ai's postinstall script was not run."`，没有 MZ/PE 头。
原文件 SHA-256：`21c366f53283d5b5e1cdbbec2aafc98286b4c1075a4c3d5afd5ce1f5c9bf46dd`。

本机 pnpm 版本为 `12.6.0`，全局 `global/v11/pnpm-workspace.yaml` 中明确存在
`allowBuilds: { opencode-ai: false }`。这解释了为什么平台原生可执行文件
已经安装，但入口仍然是不可执行的占位文本。

## 修复与验证

使用 Python 调用 Windows `IsProcessorFeaturePresent(40)`，确认支持 AVX2。
读取安装包自己的依赖解析结果，选择已安装且同版本的
`opencode-windows-x64@1.19.4/bin/opencode.exe`。预先验证源程序能返回版本号，
再用临时硬链接及原子替换恢复原入口，与官方 postinstall 的硬链接策略一致。
没有运行 PowerShell，也没有修改厂商脚本、OpenCode 用户配置或认证资料。

恢复后大小为 `211699592` 字节，PE 架构为 `0x8664`，
SHA-256 为 `41c848c0986720c02d39b015bd2672e454a221052f6947854bc508d8765d9711`。源与入口的完整 SHA-256 已比较一致。
全局构建许可仅将 `opencode-ai` 改为 `true`；没有开启所有包的脚本执行许可。

实际验证均退出 0：源程序和原报错路径直接执行 `--version`，以及经 PATH
中的 pnpm CMD 入口执行 `opencode --version`，均返回 `1.19.4`；
`opencode --help` 显示命令与选项。此版本帮助文本写到 stderr，判定同时检查
stdout、stderr 及退出码。验证覆盖 Windows 可执行文件加载与 CLI 分派；
没有执行模型请求或交互会话验收。

## 存储与本机回执

开始时 C 卷空闲 `506332418048` 字节，
闭场时 `506136289280` 字节。
复用已安装的原生程序硬链接，没有下载或复制 211 MB 的程序。
仅新增小型脚本、诊断 JSON、479 字节原占位文本及 34 字节原许可备份。
诊断及具体本机路径保存在被 Git 忽略的 `runtime/opencode-repair-20261025/`。
临时脚本按 derived 类别在闭场 48 小时后复核，原始诊断按 raw_evidence
类别在闭场 30 天后复核；不自动续期保护，也不清理其他任务资料。

## 上游依据

[pnpm approve-builds 文档](https://pnpm.io/cli/approve-builds) 说明按包批准构建脚本
及全局安装组共用的许可文件；当前机器的安装占位文本、许可和原生依赖直接提供
此次诊断依据。修复保留现有版本，没有依据历史问题降级或更换安装渠道。
