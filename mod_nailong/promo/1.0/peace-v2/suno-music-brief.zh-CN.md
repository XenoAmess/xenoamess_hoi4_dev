---
instrumental: true
status: prompt-ready-not-generated
picture_duration_seconds: 60
target_music_source_seconds: 70
---

# 给60秒和平版宣传片生成背景音乐

先完成的画面为60秒／1800帧，晓晓实际语音44.832秒，语速正常。这份说明在无配乐版实际构建、全片解码和关键帧核对之后编写。本轮没有调用Suno生成音乐，也没有把旧临时配乐混入新版。

采用[suno-engineer技能](C:/Users/Administrator/.codex/skills/suno-engineer/SKILL.md)的纯器乐流程：简洁的风格描述、三种主要乐器、少量结构标签、为旁白让出空间。技能里关于V5/V5.5和时长控件的描述较旧；当前模型和界面按2026-11-18查询的官方文档更新，不修改工具链要求字节固定的技能文件。当前没有可调用的`load_override`工具，也未在已知技能／项目位置找到`suno-preferences.md`，本片使用上述主题和用户反馈作为偏好。

要的是温和、有呼吸的电影配乐：有一点希望感，能承托和平、尊严与善意的旁白。保持克制，不做儿童卡通、滑稽配乐或战争动员式的高潮。这是本片的创作选择，不是Suno保证的效果。

## 在Suno里填写

1. 进入Create，打开Custom与Instrumental。官方的[器乐说明](https://suno.com/tools/instrumental-generator)与[Custom操作说明](https://help.suno.com/en/articles/3726721)均支持用场景、乐器、情绪和节奏描述背景音乐。
2. 选常规 **v6**；没有付费模型时可用 **v6-mini**。本片优先遵循文案与结构，因此选择常规v6；官方将v6-wild定位为更不可预测的探索版本。[当前模型说明](https://help.suno.com/en/articles/13924737-current-models-v6)
3. 名称可填“让游戏多一点温柔”。**Variety设0**，保留下面的风格方向。官方说明0可减少对输入风格的自动变化；本片无需开启Max Mode。[v6 FAQ](https://help.suno.com/en/articles/13924481)
4. 若界面仍显示Weirdness／Style Influence，可从20%／80%起步；这是本片建议值，不是官方最优参数。它们的含义见[Creative Sliders](https://help.suno.com/en/articles/6141377)。若没有这两个控件，跳过即可。
5. 若当前界面提供Duration，选约 **1:10**；没有就依靠下方“around70seconds”的提示，不必寻找旧界面控件。官方曾发布Duration控件，但当时注明V5.5；不能据此断言所有当前v6界面都有相同控件。[历史发布说明](https://suno.com/release-notes/duration-slider-on-web)

### Style / Styles

直接复制：

```text
Instrumental chamber-pop film underscore, 84 BPM, 4/4. Felt piano, lightly fingerpicked nylon guitar, restrained warm strings. Human, hopeful and understated. Sparse midrange and gentle phrasing leave clear space for Mandarin narration. A concise cue around 70 seconds, with a soft opening, a modest emotional lift and a settled piano ending. Consistent low-to-medium energy, clean acoustic production.
```

### Exclude Styles

如果有Exclude字段，填下面四项；该功能的官方入口在Custom的Advanced Options。[排除元素说明](https://help.suno.com/en/articles/3161921)

```text
no vocals, no drums, no brass, no comedy music
```

没有Exclude字段时，把这行追加到Style末尾。听成品时仍要检查有无人声或夸张音效，不能把排除提示当成硬保证。

### Lyrics

只放结构标签，不放中文宣传词、时间表或括号里的说明。若Instrumental开启后歌词框隐藏，保持隐藏即可：

```text
[Intro - restrained]
[Main Theme - hopeful, settled ending]
[End]
```

## 生成后怎么挑、怎么给我

先生成一组，听两版，选没有哼唱、没有突兀强拍、旋律不会压住说话的一版。开头应很快进入音乐，后半段稍展开即可；避免空等十几秒才进入主题。声音或情绪明显不合适时，再调整Style，不要为了精确60秒反复消耗生成次数。

音乐源目标约65–75秒，为最终60秒剪辑留出裁切余量。生成器未必按文字准确给出时长或秒级转折；即使得到较长版本，只要有完整且连贯的60秒可用段，也可以交给我处理。**不需要你提前剪成60秒。**

下载原始 **WAV** 发给我；没有WAV选项就发 **MP3**，不要录屏或转码。官方说明MP3面向所有计划，网页版WAV需Pro／Premier。[下载格式说明](https://help.suno.com/en/articles/13926081)。同时附上歌曲链接，方便核对你选的是哪一版。若两版都喜欢，可以把两个原文件都给我，不必先拼接。

收到后按固定画面做配乐剪辑与混音：0–14秒克制进入；14–27秒托住人物展示；27–33秒反歧视主标语保持平稳；33–52秒温和展开；52–60秒留出片尾收束和自然余音。这是后期目标，不要求Suno准确卡住每个时间点。最终仍为60秒，旁白位置与本版时码保持一致。

## Generation Log

2026-11-18：仅完成提示词与交接说明；未生成、未试听Suno成品、未消费Suno额度。实际音乐文件待用户提供。
