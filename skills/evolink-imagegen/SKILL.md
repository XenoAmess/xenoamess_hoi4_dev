---
name: evolink-imagegen
description: 通过 EvoLink API 生成原生透明 PNG、查询异步任务或恢复下载，并保存完整请求和原始结果。当用户选择 EvoLink 或需要维护已有 EvoLink 生图任务时使用。
---

# EvoLink 图片生成与恢复

使用随 skill 提供的纯 Python 标准库客户端 [scripts/evolink_image.py](scripts/evolink_image.py)。它支持 `gpt-image-2`、`gpt-image-2.5-sunburst`、`gpt-image-2.5-flare` 原生透明路线和 `gemini-nano-banana-2.1` 官方路线，一次请求一张，无需安装 SDK。参数和状态见 [references/protocol.md](references/protocol.md)，历史验证与代码来源见 [references/provenance.md](references/provenance.md)。

## 执行前

- 沿用用户已指定的供应商、任务范围、输出目录和项目规则。已有调用授权无需重复确认；创建 skill、读代码和预检本身不代表已获授权付费生成。HOI4 默认内置图片渠道的设置不因 skill 存在而改变。
- 区分新任务、已有 task ID 的取回和美术返修。
- 准备完整 UTF-8 prompt，明确输入图角色，实际查看需要参考的图片。现成客户端只接收公开 HTTPS 参考 URL；优先固定 commit 的 GitHub raw URL。仓库公开不代表本地参考图已公开；不自行上传本地或原版游戏素材，获授权的素材传输另行处理。
- 默认 `model=gpt-image-2`，使用 `background=transparent`、`n=1`；`gpt-image-2.5-sunburst`、`gpt-image-2.5-flare` 共用这些 GPT 参数。透明度由参数控制，prompt 描述主体、构图、风格和不变量，避免要求绘制棋盘格或绿幕。`--model gemini-nano-banana-2.1` 使用 Nano Banana 2.1 官方参数，`--resolution` 映射为该模型的 `quality=1K/2K/4K`，不发送 GPT 专属参数。其他模型、非透明输出或新参数先查所选路线当前官方文档，不冒用历史验证。
- 密钥从 `EVOLINK_API_KEY` 读取：先当前进程，再 Windows 用户级环境；交互终端可隐藏输入。密钥不进对话、命令行、文件或 Git。非交互环境缺密钥时报告配置缺口，不等待隐藏输入，不打印环境变量值。

## 新建一张

从仓库根目录用 `cmd.exe` 执行以下单行命令，替换为实际 prompt、新输出位置和参考 URL。先做本地参数预检：

```text
python skills/evolink-imagegen/scripts/evolink_image.py --dry-run --prompt-file runtime/evolink/example/prompt.txt --output runtime/evolink/example/output.png --size 2:3 --resolution 2K --quality high --image-url https://example.org/reference.png
```

预检不读取密钥、不联网、不写入尝试记录。实际调用属于已授权范围时，去掉 `--dry-run` 执行；文生图没有参考则省略 `--image-url`。多图参考重复该参数，保持顺序。

调用前保存真正发送的 prompt 原字节与去密 request，收到 task ID 后立即记录。终端 `Created task` 只表示已提交，不能报告为图片完成。每次新生成使用独立目录或新文件名，保留失败、弃用和历史结果。

## 取回已有任务

在原尝试相同输出位置恢复，不重新提交 prompt 或创建生成任务：

```text
python skills/evolink-imagegen/scripts/evolink_image.py --task-id TASK_ID --output runtime/evolink/example/output.png
```

原 `.prompt.txt`、`.request.json` 必须齐全，task ID 必须匹配。超时或下载失败先查已有 task ID，不重做 POST。POST 状态不明且没有拿到 ID 时保留归档，报告未决状态，不盲目再次计费。明确失败、额度不足、鉴权失败、限流和内容拒绝分别报告。

## 完成与交付

- 客户端验证 PNG 签名并保存返回原字节，写 SHA-256、大小和 UTC。它不修图、不修改 Alpha，也不完成美术审查。
- 单独核对 RGBA/Alpha，在白、黑或实际场景底色做正确 SourceOver 对照；检查主体、参考特征、领口及可见孔洞。252–254 或极弱边缘数值本身不能代替视觉判断。
- 交付原始 PNG、实际 prompt、request、task 和 result 记录，报告实际结果与路径。入项目素材库时遵守其 SHA、manifest、Git 和游戏验收规则；`runtime/` 输出本身不等于已入库或发布。
