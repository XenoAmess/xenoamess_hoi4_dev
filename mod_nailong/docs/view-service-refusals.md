# 查看被服务拒绝的原图

本次31项属于服务拒绝，没有返回新的生成图片。本机图览展示每项原图，并可展开实际有序输入、完整实际提示词、拒绝回执和时间。点击原图或输入可打开本机PNG；搜索框支持文件名、原路径和来源SHA。

在项目根目录用`cmd.exe`运行：

```bat
python tools\refused_source_gallery.py --open
```

默认页面为`runtime/reports/extra31-service-refusals/index.html`，依据[本轮逐项实际审计](../data/extra-retry-rounds/20261024-exhausted-high-31-completed.json)生成，渲染前重新核对所有实际输入SHA。页面通过本机文件链接读取原图，适用于有这些原图和实际输入的本机；HTML和原版图片不进入Git或游戏payload。生成器和审计记录进入Git。页面本身不代表生成成功、美术合格或游戏显示验收。

以后可指定另一份同结构审计及本机输出位置：

```bat
python tools\refused_source_gallery.py --audit PATH_TO_AUDIT_JSON --output runtime\reports\my-refusals\index.html --open
```
