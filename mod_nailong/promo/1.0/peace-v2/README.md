# 钢奶龙心：和平版宣传片

最新带音乐版已使用用户提供的《A Quiet Start》，保持60秒、晓晓配音与原画面。已添加到同一GitHub Release并核对公开下载字节：[下载带音乐版](https://github.com/XenoAmess/xenoamess_hoi4_dev/releases/download/nailong-v1.0-20261105/gangnailongxin-1.0-peace-xiaoxiao-a-quiet-start-60s-v3.mp4) · [混音与验收回执](music-finish-receipt-20261118.json)。以下保留无配乐版的制作说明。

新版已完成，画面时长固定为**60秒**：1920×1080、30fps、1800帧。旁白改用实际生成的Edge TTS **晓晓（zh-CN-XiaoxiaoNeural）**，正常语速。12句语音共44.832秒，保留句间停顿与标语阅读时间；本版没有配乐。

按用户2026-11-18的明确要求，已上传到现有GitHub Release，并从公开链接下载核对大小和SHA-256。[下载60秒晓晓无配乐版](https://github.com/XenoAmess/xenoamess_hoi4_dev/releases/download/nailong-v1.0-20261105/gangnailongxin-1.0-peace-xiaoxiao-60s-voiceonly-v2.mp4) · [发布回执](video-publication-20261118.json)

文案依据创意工坊“让游戏多一点温柔”“游戏是游戏，现实是现实”重写，围绕现实和平、反对种族歧视、尊重人的尊严，以及不把游戏敌我关系投射到现实人群。删去旧版开会和忍笑段子，保留头像模组及服装、发型、胡须、神态等产品细节。中国相关人物不作为重点的选角偏好继续保留。

本机视频：`runtime/promo-peace-20261118/build-001/gangnailongxin-peace-xiaoxiao-voiceonly-v2.mp4`。字幕：`runtime/promo-peace-20261118/prepared-001/narration.zh-CN.srt`。

- [新版导演稿与旁白](director-script.zh-CN.md)
- [完整旁白输入](narration.zh-CN.json)
- [实测时长与验收回执](revision-receipt-20261118.json)
- [最后编写的Suno音乐生成说明](suno-music-brief.zh-CN.md)

实际XAR plan/build通过，全片解码返回0，真峰值−7.5dBFS，逐句provider边界文本及音频时长核对通过。17张编码帧已作有限目视检查；原生audit只验证字节与所选帧证据完整性。精确字节probe与pending review包已生成并留存。没有记录具名人工完整观看或听审；制作回执保留上传前的历史状态，之后的公开上传事实另见发布回执。

先做完了文案、晓晓配音与固定60秒的剪辑，再查询现行Suno官方说明，编写音乐提示词。该阶段未调用Suno或消费其额度。之后用户提供《A Quiet Start.wav》，已按固定画面完成淡入淡出、平滑压低音乐和连续音轨混音；不需要重新决定片长。输入WAV实际59.56秒，保留完整时间范围并补0.44秒静音。

既有录屏与高清美术只作来源复用，没有重新操作Steam／游戏或修改PNG母版。旧75秒视频与GitHub附件保持历史字节；制作与发布旧记录继续保存。
