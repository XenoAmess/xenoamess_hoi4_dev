# OCR 与键鼠工作流

只通过截图、OCR、真实鼠标与键盘完成 Steam、Launcher 和 HOI4 界面交互。没有 MCP、UI Automation、内存桥或隐藏业务接口。

```text
python tools/desktop.py observe --output runtime/current.png --ocr
python tools/desktop.py click --screenshot runtime/current.png --content-rect 0 0 <原图宽> <原图高> --x <原图X> --y <原图Y> --hwnd <目标窗口HWND> --receipt runtime/click.json
python tools/desktop.py observe --output runtime/after-click.png --ocr
```

查看缩略图时 `--content-rect` 必须改成实际预览内图像内容矩形，坐标也使用该矩形内的预览值。X/Y 独立映射；截图与当前桌面尺寸不一致、过旧或点位越界即拒绝。回执保存图像 SHA、内容矩形、坐标、HWND、桌面尺寸和时间。

`keys` 子命令支持单键、组合键、`--text` 与 `--text-file`；先焦点核验并切换/读回目标线程的 `LANGID=0x0409`。文本输入前先 Ctrl+A，粘贴后通过实际 Ctrl+A/Ctrl+C 复制读回全文并精确比较，匹配才返回成功；这是 OS 剪贴板和真实键盘操作，不调用控件接口。按键后仍需新图/OCR 核对页面实际结果，输入 ACK 不等于业务成功。

OCR 使用本机已安装 Windows OCR 语言，优先中文。没有可用语言时保留截图并停止 OCR，不调用系统在线安装命令，也不更改 Steam 状态。截图里有隐私内容时留在忽略的 `runtime/`，公开报告只存必要摘要。

Steam 离线证据必须是当前机器的新截图，并直接审图确认。若图像重复或时钟停滞，先通过正常窗口变化证明新鲜度；不能仅以文件写入时间确认。禁止点击“上线”来做无关开发。
