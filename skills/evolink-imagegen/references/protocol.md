# 协议与回执

此 skill 的客户端支持 `gpt-image-2`、`gpt-image-2.5-sunburst`、`gpt-image-2.5-flare` 原生透明路线和 `gemini-nano-banana-2.1` 官方路线，不是任意模型 SDK。新调用的路线或服务条件有变化时，核对 [官方文档](https://docs.evolink.ai/)。

| 用途 | 方法与地址 |
| --- | --- |
| 创建 | `POST https://api.evolink.ai/v1/images/generations` |
| 查同一任务 | `GET https://api.evolink.ai/v1/tasks/{task_id}` |
| 下载 | GET 首个结果 URL；不向 CDN 发送 API 鉴权头 |

创建和查询使用 Bearer 鉴权。GPT Image 2 与 2.5 Sunburst/Flare 创建体使用对应 model、`background=transparent`（可用 `--background opaque` 改为 opaque）、`n=1`。Nano Banana 2.1 创建体使用 `model=gemini-nano-banana-2.1`，将 CLI 的 `--resolution` 映射为 `quality=1K/2K/4K`，不发送 `background`、`n` 或 GPT 的 `resolution` 字段。

| CLI | 请求字段或用途 | 默认 |
| --- | --- | --- |
| `--prompt-file` | UTF-8 完整 prompt，保留首尾空白 | 新建必填 |
| `--model` | `gpt-image-2`、`gpt-image-2.5-sunburst`、`gpt-image-2.5-flare` 或 `gemini-nano-banana-2.1` | `gpt-image-2` |
| `--output` | 用户授权目录中的新 `.png` 路径 | 必填 |
| `--image-url`，可重复 | 有序 `image_urls` | 空数组 |
| `--size` | `size`，例如 `2:3`、`1:1` | `2:3` |
| `--resolution` | 1K、2K、4K | `2K` |
| `--quality` | low、medium、high | `high` |
| `--background` | GPT 路线输出 transparent 或 opaque | `transparent` |
| `--poll-seconds` | 正数查询间隔 | 5 秒 |
| `--timeout-seconds` | 正数轮询墙钟上限 | 600 秒 |
| `--task-id` | 恢复，只查询和下载 | 无 |
| `--dry-run` | 新请求本地预检，无网络、密钥读取或写入 | 关闭 |

客户端支持这些值不证明每种组合都有服务资格或已实测。不发送上游未使用的 `output_format`、`response_format`；新增字段先查所选当前路线。

参考 URL 的校验是本客户端约定：HTTPS、有域名，不含 username/password/query/fragment。它不提供上传功能，不接受本地路径；拒绝签名 query 不代表整个 EvoLink API 都禁止这种输入。公开素材优先使用固定 commit URL，并先确认授权及可访问性。

在 `output.png` 旁追加保存：

| 文件 | 内容 |
| --- | --- |
| `output.prompt.txt` | 与实际 prompt 的 UTF-8 编码逐字节一致 |
| `output.request.json` | endpoint 和实际请求体，无密钥或鉴权头 |
| `output.task.json` | 可恢复的非秘密 task ID，无临时下载 URL |
| `output.png` | 返回的未经重编码原始 PNG |
| `output.result.json` | task ID、原图 SHA-256、bytes、下载 UTC 和 PNG 签名结果 |

新建拒绝覆盖已有尝试；恢复要求原 prompt/request 齐全、已有 task ID 不变、原图尚不存在。已有图但结果侧录缺失时核对原图再补小型回执，不重新生成或覆盖。

轮询活动状态为 pending/queued/processing/running，成功状态为 completed/succeeded/success；仍必须拿到结果 URL 和 PNG。默认创建/轮询 HTTP 超时各 60 秒、下载 120 秒；600 秒只覆盖轮询，不是整个 CLI 的硬墙钟上限。

下载发送 Accept、浏览器 User-Agent 和 EvoLink Referer。历史 CDN 403 曾经由这些头修复，并从同一 task 取回；不保证所有未来 403 都能修复。

脚本不自动重做 POST、不重提失败任务。失败、鉴权、余额、限流或内容拒绝直接报告。HTTP 错误显示状态和响应类型，不倾倒服务完整响应或签名 URL。原图艺术质量、真实 Alpha、项目许可、费用和服务端并发均不能由客户端成功退出自动证明。
