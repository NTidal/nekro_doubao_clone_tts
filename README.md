# 豆包声音复刻语音插件 (nekro_doubao_clone_tts)

NekroAgent 插件：调用火山方舟「声音复刻（Voice Clone）」能力，用**已训练好的克隆音色**把文本合成为语音，
发送到群聊/私聊。支持 **OneBot V11** 与 **QQ 官方机器人（qqbot_openclaw）** 两种渠道。

版本：**1.1**　作者：**NTidal**　适配器：**onebot_v11** / **qqbot_openclaw**

---

## 渠道差异（重要）

两种渠道的发语音机制完全不同，**音频格式要求也不一样**：

| | OneBot V11 | QQ 官方机器人（qqbot_openclaw） |
|---|---|---|
| 发送方式 | `record` 段（`send_group_msg` / `send_private_msg`） | 音频落盘 → `send_file()` → 适配器按后缀判定 `file_type=3` → 官方分片上传 → `msg_type=7` |
| 音频格式 | `mp3` / `ogg_opus` / `pcm` 均可（协议端会自动转 silk） | 用 **`mp3`**；`pcm` 会被当成**文件**发送 |
| 依赖 | 协议端需有 ffmpeg 才能转码 | **无需 ffmpeg、无需转 silk** |
| `SEND_MODE` | 生效（`base64` / `file`） | **忽略**（固定走文件上传流程） |

> **QQ 官方渠道实测结论**（2026-10-06，群聊场景）：
>
> - `mp3`(16k/24k) / `wav` / `flac` / `m4a` / `ogg` / `amr` / `aac` 均被平台接受，客户端渲染为**带时长的语音气泡**
>   （已由用户在群里确认「两条七秒的语音」）；**mp3 直发即可，不需要转 silk** ——
>   这一步省掉了整条 ffmpeg + silk 编码器依赖链。
> - `.silk` 必须带腾讯特有的 `0x02` 前缀（`pilk.encode(..., tencent=True)`）；
>   缺该前缀的裸 silk 会被平台以 `850019 富媒体文件格式不支持` 拒收。
>   **平台校验的是文件内容魔数，与扩展名无关**（把带 0x02 的 silk 命名为 `.mp3` 同样通过）。
> - `.pcm` 不在适配器音频后缀白名单里，会被判成 `file_type=4`（文件）而不是语音；
>   插件遇到该格式会**显式报错并提示改用 mp3**，不会静默发成文件。
> - 发音频**必须走 `send_file()`**，不能用 `send_image()`（后者会被强制判成 `image` 类型）。

---

## 功能

- 🎙️ **克隆音色语音合成**：通过通用 ICL 合成端点
  `https://openspeech.bytedance.com/api/v3/tts/unidirectional`（资源 ID `seed-icl-2.0`），
  使用事先训练好的 `S_` / `icl_` 音色合成语音。
- 🔀 **双渠道自动分派**：按会话的 `adapter_key` 自动选择发送方式，同一份配置可在
  OneBot V11 与 QQ 官方机器人上同时使用。
- 🤖 **LLM 工具调用**：注册沙箱方法 `send_voice_clone(chat_key, text, speaker_id="")`，
  人设/对话中由模型自主决定何时发语音；`speaker_id` 留空即用配置里的默认音色，
  LLM 只需 `send_voice_clone(chat_key, text)` 一个调用即可发声。
- 🎲 **语音概率触发**：按配置概率向 LLM 注入语音提示，引导其偶尔用语音回复；
  支持超长用户消息自动抑制，控制合成消耗。
- 🛠️ **合成参数可调**：音频格式、采样率、语速、音量、最大字符数、超时、输出目录、发送方式全部可配置。
- 📤 **两种发送方式**：`base64`（内嵌数据，跨机器最稳）/ `file`（本地路径，需与协议端共享文件系统）；**仅 OneBot V11 生效**。

> 音色的**训练**不在本插件范围内。请先在火山方舟控制台（或其他途径）完成声音复刻训练，
> 拿到 `S_` / `icl_` 音色 ID 后填入配置或调用时传入。

---

## 前置条件

1. 已部署 **NekroAgent**，并接入 **OneBot V11**（如 NapCat）或 **QQ 官方机器人（qqbot_openclaw）**。
2. **火山方舟 API Key**，且该 Key 已开通**声音复刻**资源（`seed-icl-2.0`）。
3. 已训练完成的声音复刻音色 ID（`S_` / `icl_` 开头）。

> 用 QQ 官方机器人时**无需**额外安装 ffmpeg 或 silk 编码器（见上文渠道差异）。

---

## 安装

1. 将 `doubao_tts_voice.py` 放入 NekroAgent 插件目录，或在 NA WebUI 打包上传安装。
2. **完全重启 NekroAgent**（插件配置与沙箱方法在启动时注册）。
3. NekroAgent WebUI → 插件 → 「豆包声音复刻语音插件」→ 配置：
   - 必填 **API Key**（火山方舟通用 Key，需已开通声音复刻资源）；
   - 按需修改 **默认克隆音色 ID**（默认值为占位示例 `S_xxxxxxxx`，请替换为你在火山方舟训练得到的音色）。
4. 保存后即可使用，无需其他依赖。

---

## 配置项

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `API_KEY` | 空（**必填**） | 火山方舟 API Key（通用 Key，需开通声音复刻资源 `seed-icl-2.0`） |
| `VOICE_CLONE_TTS_URL` | `https://openspeech.bytedance.com/api/v3/tts/unidirectional` | 克隆音色合成地址（POST），可改 |
| `VOICE_CLONE_RESOURCE_ID` | `seed-icl-2.0` | 克隆音色合成资源 ID |
| `VOICE_CLONE_API_KEY` | 空 | 复刻专用 Key，留空则复用 `API_KEY` |
| `CLONE_DEFAULT_SPEAKER` | `S_xxxxxxxx`（占位） | 默认克隆音色 ID（`S_`/`icl_` 开头）；调用不传 `speaker_id` 时使用，**必须替换为自己的音色** |
| `VOICE_TRIGGER_PROBABILITY` | `0.3` | 每次对话以该概率向 LLM 注入语音提示（0~1，0 关闭） |
| `VOICE_TRIGGER_PROMPT` | 内置提示词 | 命中概率时注入的语音提示，措辞可自定义 |
| `VOICE_TRIGGER_MAX_INPUT_LENGTH` | `100` | 用户消息超过该长度则不触发语音（防长消息高消耗）；0 表示不限制 |
| `VOICE_COOLDOWN` | `60` | 语音冷却（秒）：发送语音后的冷却期内**不进行触发概率计算**（不注入语音提示）；**不会拒绝语音请求**；0 表示不启用 |
| `VOICE_DEDUP_WINDOW` | `300` | 内容防抖窗口（秒）：窗口内与上一条语音**内容高度相似**的请求会被**静默忽略**（不发送任何消息、对 LLM 返回成功，不影响本回合文字输出）；0 表示不启用 |
| `VOICE_DEDUP_SIMILARITY` | `0.6` | 防抖相似度阈值（0~1）：文本规范化后与上一条语音相似度达到该值即判重；**互为子串（含相等）直接判重** |
| `AUDIO_FORMAT` | `mp3` | 音频格式：`mp3` / `ogg_opus` / `pcm`。**QQ 官方渠道请用 `mp3`**（`pcm` 会被当成文件发送而非语音条） |
| `SAMPLE_RATE` | `24000` | 采样率：8000 / 16000 / 22050 / 24000 / 32000 / 44100 / 48000 |
| `SPEECH_RATE` | `0` | 语速 [-50, 100]：100 = 2.0 倍速，-50 = 0.5 倍速 |
| `LOUDNESS_RATE` | `0` | 音量 [-50, 100]：100 = 2.0 倍音量，-50 = 0.5 倍音量 |
| `MAX_TEXT_LENGTH` | `300` | 单次最大合成字符数（超出截断） |
| `REQUEST_TIMEOUT` | `60` | 合成请求超时（秒） |
| `OUTPUT_DIR` | `./data/nekro_agent/plugins/doubao_tts_voice` | 音频输出目录（`file` 发送方式下使用） |
| `SEND_MODE` | `base64` | 发送方式：`base64`（推荐）/ `file`。**仅对 OneBot V11 生效**；QQ 官方机器人固定走文件上传流程，忽略此项 |

---

## 使用方式

**LLM 工具调用（主要用法）**

插件向沙箱注册 TOOL 方法：

```python
send_voice_clone(chat_key, text, speaker_id="")
```

- `chat_key`：会话标识，形如 `onebot_v11-group_123456`（由框架提供，LLM 无需关心）。
- `text`：要合成发送的语音文本（口语化、不宜过长）。
- `speaker_id`：可选，克隆音色 ID；留空使用 `CLONE_DEFAULT_SPEAKER`。

成功返回 `True`，失败返回 `False`（错误详情见 NekroAgent 日志）。

**语音概率触发（辅助）**

每轮对话按 `VOICE_TRIGGER_PROBABILITY` 概率向 LLM 注入 `VOICE_TRIGGER_PROMPT`，
引导模型在该轮用克隆音色语音回复；用户消息超过 `VOICE_TRIGGER_MAX_INPUT_LENGTH` 时自动跳过。
不需要随机语音时把概率设为 `0`，模型仍可在判断合适时主动调用 `send_voice_clone`。

**语音冷却（只管概率触发）**

发送语音成功后该频道进入 `VOICE_COOLDOWN`（秒）冷却期：冷却期内**不进行触发概率计算**（不注入语音提示）。
冷却**不会拒绝**语音请求——用户主动要求的语音、LLM 判断合适的语音随时可发；
设为 `0` 关闭冷却。

**内容防抖（静默吞掉流式连发）**

LLM 流式输出有时会在一个回合内连着请求两条内容相近的语音。为此插件对每次请求做**内容级去重**：

- 将文本**规范化**（剔除标点/空白/装饰符号、去掉句尾叠词语气词、转小写）后，与该频道上一条语音的规范化文本比较；
- 相似度（`SequenceMatcher` 比率）达到 `VOICE_DEDUP_SIMILARITY`（默认 0.6）即判重；
- **互为子串（含完全相等）直接判重**——覆盖"先发半句、再发全句"这类流式截断场景；
- 判重窗口为上一条语音发出后的 `VOICE_DEDUP_WINDOW` 秒（默认 300），窗口外不比较；
- 按频道独立记录。

**防抖命中时的行为：静默忽略**

判重命中的请求**不会**返回失败，也**不会向聊天发送任何消息**（聊天里不出现语音条）：

1. 不调用合成 API（零消耗），不产生任何群内消息；
2. 对 LLM **返回成功**——本回合内后续的文字输出完全不受影响，AI 不会哑火、不会向用户解释"被拒绝了"；
3. 日志记录 `内容防抖命中（相似度 X.X）`，仅在 NA 运行日志可见。

这样防抖对用户和 LLM 都是透明的：连发的第二条"消失"了，对话照常进行。

---

## 常见问题

**`requested resource not granted`**
该 API Key 未开通「声音复刻」资源（`seed-icl-2.0`）。到火山方舟控制台为对应 Key 开通声音复刻服务后重试。

**返回 401 / 鉴权失败**
检查 `API_KEY` 是否填写正确；若使用独立的复刻 Key，确认 `VOICE_CLONE_API_KEY` 配置。

**调用成功但群里没有语音**
- OneBot V11：确认协议端在线且支持发送 `record` 消息；协议端（如 NapCat）需要可用的 ffmpeg 才能转码发送语音，请检查协议端日志；默认 `base64` 发送方式兼容性最好，改用 `file` 时需保证 NekroAgent 与协议端共享文件系统路径。
- QQ 官方机器人：确认 `AUDIO_FORMAT` 是 `mp3`（`pcm` 会被当成文件、不显示为语音条）；查看 NA 日志里是否有 `850019 富媒体文件格式不支持`（silk 缺 `0x02` 前缀时会这样）。

**QQ 官方渠道报 `850019 富媒体文件格式不支持`**
平台按**文件内容魔数**校验，不是按扩展名。若音频是 SILK，必须带腾讯特有的 `0x02` 前缀
（`pilk.encode(..., tencent=True)`）；`pilk` 默认 `tencent=False` 产出的标准 SILK 恰好会被拒收。
**建议直接用 mp3**，绕开整个 silk 依赖链。

**QQ 官方渠道：`AUDIO_FORMAT` 设成 `pcm` 会怎样**
插件会**显式报错**并提示改用 mp3，而不是静默把它当文件发出去
（`.pcm` 不在适配器音频后缀白名单内，会被判成 `file_type=4`）。

**语音触发太频繁 / 从不触发**
调整 `VOICE_TRIGGER_PROBABILITY`（0~1）；同时注意 `VOICE_TRIGGER_MAX_INPUT_LENGTH` 的抑制逻辑，
长消息场景默认不发语音。若刚发过语音后一段时间内不再触发，属 `VOICE_COOLDOWN` 冷却正常行为。

**LLM 调用 send_voice_clone 返回 False**
只剩三种情况：文本/音色为空、API Key 未配置、合成接口报错——内容防抖命中的请求**不会**返回 False
（静默吞掉并返回成功），时间冷却也**不会**拒绝调用。排查时看日志中的「克隆音色合成/发送失败」行。

**音色 ID 从哪里获得**
在火山方舟控制台完成声音复刻训练后获得（`S_` / `icl_` 开头）。训练流程不属于本插件范围。

---

## 说明

- 已适配 **onebot_v11** 与 **qqbot_openclaw**；其他适配器未做适配（调用时会明确报「暂不支持」而不是静默失败）。
- 语音合成按量计费（火山方舟侧），请合理设置 `MAX_TEXT_LENGTH` 与触发概率控制消耗。
- 合成失败、发送失败均记录到 NekroAgent 日志（前缀含 `[chat_key]`），排查时先看日志。

## 更新日志

### 1.1

- **新增 QQ 官方机器人（qqbot_openclaw）渠道支持**。原实现硬编码 OneBot
  （`MessageSegment.record` + `send_group_msg`），在官方渠道上完全不可用；
  现改为按 `adapter_key` 分派：

  ```
  _send_voice_record(_ctx, chat_key, audio_bytes)
    ├─ qqbot_openclaw → 音频落盘为 .mp3 → _ctx.fs.mixed_forward_file()
    │                    → send_file() → file_type=3 → 官方分片上传 → msg_type=7
    └─ onebot_v11     → 原有 record 逻辑
  ```

- `support_adapter` 增加 `"qqbot_openclaw"`。
- `get_bot` 由模块级硬导入改为函数内导入 —— 纯 QQ 官方渠道部署时 OneBot 模块不可用，
  原先会导致整个插件导入失败。
- 新增 `.pcm` 防护：该后缀不在适配器音频白名单，会被静默发成文件；现在显式报错并提示改用 mp3。
- 补充 `AUDIO_FORMAT` / `SEND_MODE` 的渠道差异说明（`SEND_MODE` 仅对 OneBot 生效）。
- README 增加《渠道差异》一节，含实测格式矩阵与 silk `0x02` 前缀结论。

### 1.0

- 首个版本：克隆音色合成 + OneBot V11 发送 + 概率触发 + 冷却 + 内容防抖。

## 版权

MIT
