# 来源与验证范围

源仓库为 [XenoAmess/slay-the-spire-vivhite-mod](https://github.com/XenoAmess/slay-the-spire-vivhite-mod)，固定 master `94559b5a80ef4bdec8ff8a58042256902d8df713`。

- [原始客户端](https://github.com/XenoAmess/slay-the-spire-vivhite-mod/blob/94559b5a80ef4bdec8ff8a58042256902d8df713/tools/art/evolink_transparent_image.py)，Git blob `66b131d901e98c062ca1b31a18b2cd873fcc9aec`。
- [原生透明实验](https://github.com/XenoAmess/slay-the-spire-vivhite-mod/blob/94559b5a80ef4bdec8ff8a58042256902d8df713/docs/2026-08-28-EvoLink-GPT-Image-2原生透明实验.md)，包含三次历史输出、第二次身份根接受和同一任务的 CDN 403 恢复记录。
- 上游 GPL v3 许可证保存在 [../LICENSE](../LICENSE)。本目录的改编客户端标注 GPL-3.0-only；不据此改变仓库其他文件的许可。

2026-10-25（北京时间）为可移植 skill 调整：移除白绮专属输出根，改用任务授权路径；非交互环境缺密钥直接报告；增加无网络、无密钥读取、无写入的 dry-run；实际 prompt 保留完整 UTF-8 字节和首尾空白；校验正数轮询参数；增加原始 PNG 的 SHA、大小和下载 UTC；错误输出不倾倒服务正文或临时 URL。模型、原生透明参数、单张请求、同任务恢复、公开 URL 输入和 PNG 签名校验沿用上游实现。

本次验证使用本地参数预检和模拟 HTTP 行为测试，没有读取真实 API Key，也没有付费生成。上游历史成功不能证明本机余额、当前模型资格、真实吞吐或服务端并发。

历史首张 RGBA8 为 1680×2512，四角 Alpha 为 0、主体约 253、最大 254；该图因对应用途的光晕问题归档。原生透明输出和美术通过分别判断，不能仅凭最大 Alpha 254 拒绝。

上游“同语义最多八次调整词尝试”和“透明图唯一 EvoLink”属于它的项目规则，不作为本通用 skill 的固定额度或跨项目调用授权。HOI4 的默认内置工具、高清原图与八小时冻结请求重试继续以本项目 AGENTS 为准。
