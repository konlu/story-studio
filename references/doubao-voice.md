# 豆包配音与后续制作

用于用户要求配音、文案转MP3，或完整口播流程尚无最终配音时。只维护技能时不合成音频；不复制其他技能的个人音色、凭据、草稿路径或画幅。

## 用户使用流程

文案定稿 → 选择豆包配音或提供已有配音 → 配置并确认音色 → MP3 → Coli本地SRT与音文核对 → 带时间分镜 → 配图 → 剪映草稿。

保留写作、配图、剪映草稿三个主开关；配音是可独立调用的衔接步骤，记录voice_mode=doubao、provided或none。只写稿时交付稿件，并提示可继续豆包配音，不发送付费请求；用户明确不要配音时不追问。

口播流程缺少可用的本期最终音频时，必须先执行[总入口的两条路径选择](../SKILL.md#缺少最终配音时必须先给出两条路径)：主动同时提供“配置豆包并由Agent生成MP3”和“用户自备本期最终MP3”。仅说“缺音频，请提供MP3”不算完成引导；用户只要求配图与剪映草稿、没有点名配音，也应提示。用户已选方式或已有可用音频时不重复询问；仅维护技能时不触发配音选择。禁止复用旧素材的项目不使用旧配音。

选择豆包后进入以下配置步骤，不要求用户先在其他软件生成文件；选择自备配音后接收文件或路径，由Agent完成Coli转录。等待选择期间只继续不依赖音频的工作，不默认同意合成。已有最终MP3且允许用于本期时直接核验并转录，不重复付费合成。

## 第一次必须配置的内容

向用户一次说明以下三项，并尽量合并询问本期音色、配图画风和数量；已给出的信息不重问。

| 配置项 | 用户从哪里获取 | 用途 |
| --- | --- | --- |
| 语音API Key | [豆包语音控制台API Key管理](https://console.volcengine.com/speech/new/setting/apikeys) | 对应X-Api-Key；使用语音服务的Key |
| speaker ID | [语音控制台](https://console.volcengine.com/speech/new)的音色库 | 准确音色标识，不用音色显示名称替代；确认账号有权使用该音色 |
| 模型资源resource_id | 根据已开通服务和音色选择 | 普通2.0音色用seed-tts-2.0；声音复刻2.0用seed-icl-2.0 |

“模型”有两个不同字段：必选的resource_id决定服务资源；req_params.model是复刻音色的可选细分模型参数。官方当前文档给出的默认细分模型为seed-tts-2.0-standard；普通音色不传model，复刻音色仅在用户明确选定或控制台需要时传入。不要把Ark文本模型ID、App ID、字幕Key或音色ID当作resource_id；不要求新版API Key用户额外提供App ID或Access Token。

用户需自行开通语音服务并保证资源可用，Agent负责配置本地调用端。音色和资源是否匹配以其账号控制台及真实接口结果为准，不能仅凭名称保证匹配。首次不要默认克隆任何人的声音或创建复刻任务。

可使用这样的引导：

> 文案已定稿，可以继续生成豆包配音。请在语音控制台开通对应服务，并通过宿主的安全输入/密钥配置入口提供语音API Key；同时告诉我音色speaker ID和模型资源（普通2.0或复刻2.0）。我会配置并生成MP3，然后接续Coli转录、配图和剪映草稿。已有最终配音也可以直接复用。

## 配置由Agent完成

先按[初始化流程](setup.md)检查/配置features=tts；后面还需转录和草稿时用tts,asr,draft,images。缺少的Python、websockets和FFmpeg由Agent安装，不要求用户执行命令。依赖安装不需要语音Key，也不会发送收费测试。

API Key优先从宿主安全配置的DOUBAO_TTS_API_KEY读取。只检查存在性，不显示值；不要要求在公开聊天中粘贴Key。若用户已经通过可用的保密渠道提供Key，且同意在当前电脑保存，Agent可用voice_settings.py的--key-stdin从标准输入写入专用凭据文件，不把Key放到命令参数、shell历史、项目JSON或日志。--prompt-key仅用于宿主能直接提供隐藏输入的交互终端，不要求用户自行打开终端。没有保密输入能力时引导到宿主密钥/环境变量面板，不能伪称已配置。

Agent使用初始化记录的Python绝对路径运行：

```text
"<配置的Python>" "<技能绝对路径>/scripts/voice_settings.py" check
"<配置的Python>" "<技能绝对路径>/scripts/voice_settings.py" configure --speaker "<用户的speaker ID>" --resource-id "<用户选择的resource_id>"
```

复刻音色明确需要细分模型时加--model。若要保存已授权的Key，在configure命令加--key-stdin并通过进程标准输入传入；不能使用带实际密钥的--api-key参数。仅保存音色时缺少Key会返回未就绪状态，音色配置仍已保存。check不联网，只返回Key是否存在、非秘密的音色参数和network_verified=false。

音色参数保存到用户数据目录story-studio/voice.json，与runtime.json分开。可选Key保存到同一专用目录：Windows使用当前用户DPAPI加密文件；macOS/Linux是权限0600的本地私密文件，保存前说明这一点，用户不愿保存时直接复用宿主密钥环境变量。源码目录拒绝写入这些配置；发布、打包或提交代码时不包含用户数据目录。

## 本期确认与生成MP3

每个新项目在首次生成前展示准确speaker ID、resource_id、可选model、语速（默认0）、音量（默认0）和朗读范围。用户本次已明确确认上述音色用于生成时不重复询问；历史保存配置可作为候选，不能自动代替本期确认。确认后记录在项目voice.json，不含Key。只朗读定稿正文；source.txt保存原稿，narration.txt保存实际送入内容，标题、注释是否朗读按本次请求处理。

```text
"<配置的Python>" "<技能绝对路径>/scripts/doubao_tts.py" --text-file "<项目>/narration.txt" --output "<项目>/narration.mp3" --dry-run
"<配置的Python>" "<技能绝对路径>/scripts/doubao_tts.py" --text-file "<项目>/narration.txt" --output "<项目>/narration.mp3" --voice-confirmed
```

dry-run仅核验本地文本和音色参数，不读取Key、不联网；成功不表示鉴权或额度已验证。只有实际获得确认才能加--voice-confirmed。脚本使用用户指定文档的V3双向WebSocket接口，不静默切换到SSE、旧版鉴权、其他音色或其他服务。

脚本以不丢字符的文本流发送全文，等到SessionFinished并收到音频后才视为服务完成，再用ffprobe和ffmpeg完整解码校验，保留失败的partial供排查。输出MP3及同名.voice.json，记录文本哈希、音色、协议、音频哈希和时长，不写Key。默认不覆盖已有MP3；同稿同音色先检查已有成功文件，避免再次收费。

传输分块不是服务总长度承诺。超长文案先核对当前官方限制；确需多会话时由Agent按句/段拆分，保存顺序、正文及哈希，只续做尚未成功的片段，不能摘要、漏句或截断。独立MP3片段使用ffmpeg concat demuxer合并，不能二进制拼接文件；对最终合并音频重新完整解码，并且Coli只识别最终版本。

鉴权、额度、资源或音色错误时停在配音阶段，提示具体缺口，保留已完成文稿。网络超时或不完整流可能已计费，脚本不自动重试；Agent先核对partial、已有MP3及控制台请求状态，明确是否需要重新合成。MP3已成功但后续转录/生图失败时只续做下游。

## 可选：Seed-Audio 音效与配乐

需要环境声、音效、配乐或整段氛围音轨时使用，模型 `seed-audio-1.0`，走 HTTP `https://openspeech.bytedance.com/api/v3/tts/create`。它按提示词直接生成音频（可包含人声），与人声TTS是两条独立接口，不替代本期口播配音，也不产生字幕。

```text
printf '%s' '<Key>' | "<配置的Python>" "<技能绝对路径>/scripts/seed_audio_tts.py" configure --key-stdin
"<配置的Python>" "<技能绝对路径>/scripts/seed_audio_tts.py" check
"<配置的Python>" "<技能绝对路径>/scripts/seed_audio_tts.py" generate --text-file "<项目>/sfx.txt" --output "<项目>/audio/sfx-01.mp3" --dry-run
"<配置的Python>" "<技能绝对路径>/scripts/seed_audio_tts.py" generate --text-file "<项目>/sfx.txt" --output "<项目>/audio/sfx-01.mp3" --confirm-billable
```

- 鉴权同时需要 `X-Api-Key` 与 `X-Api-Resource-Id: seed-audio-1.0`，脚本自动带上。缺少resource头时网关返回45000000并声称app key不存在，不能据此判定Key失效或要求用户重新取Key。
- Key保存在用户数据目录的独立凭据文件，与DOUBAO_TTS_API_KEY分开；不在命令参数、shell历史、项目JSON或日志中出现。环境变量`SEED_AUDIO_API_KEY`优先。
- 默认MP3、48000Hz、声道与码率由服务决定；可调format、sample_rate、pitch/speech/loudness rate（-50..100）。输出拒绝覆盖已有文件，拒绝写入技能目录，扩展名必须与format一致。
- dry-run只核验文本与参数，不读取Key、不联网、不计费。实际请求按生成音频时长计费；401/403等4xx不计费，5xx或网络中断按可能已计费处理。脚本不自动重试。
- 生成后用ffprobe复核codec、采样率、声道、时长与字节数；未试听不称听过。返回的签名URL默认不打印，确需交付链接时才加--print-url。
- 与人声分开生成时，音轨按最终配音的SRT时间轴对齐后再进草稿；单独用它生成含人声的整段音频时，仍以Coli转录结果核对文句，不把“有声音”当作口播正确。

## 接续转录、配图与草稿

1. 检查MP3完整解码、正文开头结尾、专名发音与漏读；未试听不称听过。再调用内置[配图模块](../modules/history-image/GUIDE.md)的Coli脚本，识别最终MP3，保留音频哈希与原始结果，对照文案修正错字。
2. 使用真实SRT与上下文确定分镜时间，重复句消歧，不按字数或镜数均分时长；实际生图仍需遵守本次配图开关、画风和数量选择。
3. 调用内置[草稿模块](../modules/render-history-video/GUIDE.md)，传同版MP3、核验SRT、分镜与实际图片，沿用本项目画幅；默认仍为9:16，不继承参考技能的16:9。字幕用于定位不等于上屏。

豆包人声TTS这里只负责口播，始终enable_subtitle=false；Seed-Audio音轨是可选补充，同样不产生字幕。字幕使用本机Coli，不调用或恢复已停用的火山字幕API及其凭据。交付MP3、SRT、图片和草稿时区分实际生成、结构验证、试听和剪映预览范围。

协议及参数依据：[用户指定的豆包双向WebSocket官方文档](https://docs.volcengine.com/docs/DoubaoVoice/bidirectional-streaming-text-to-speech-websocket?lang=zh)、[官方协议附件](https://portal.volccdn.com/obj/volcfe/cloud-universal-doc/upload_5ec6e28945592c909158dc1e2cf9a89c.zip)、[websockets客户端文档](https://websockets.readthedocs.io/en/15.0.1/reference/asyncio/client.html)。本项目自行实现所需二进制帧与流程，不内嵌官方协议附件源码。
