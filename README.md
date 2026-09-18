# 豆包声音复刻语音插件 (nekro_doubao_clone_tts)

NekroAgent 插件：调用火山方舟「声音复刻（Voice Clone）」能力，用**已训练好的克隆音色**把文本合成为语音，
经 OneBot V11 以 `record` 语音消息发送到群聊/私聊。

版本：**1.0**　作者：**NTidal**　适配器：**onebot_v11**

---

## 功能

- 🎙️ **克隆音色语音合成**：通过通用 ICL 合成端点
  `https://openspeech.bytedance.com/api/v3/tts/unidirectional`（资源 ID `seed-icl-2.0`），
  使用事先训练好的 `S_` / `icl_` 音色合成语音。
- 🤖 **LLM 工具调用**：注册沙箱方法 `send_voice_clone(chat_key, text, speaker_id="")`，
  人设/对话中由模型自主决定何时发语音；`speaker_id` 留空即用配置里的默认音色，
  LLM 只需 `send_voice_clone(chat_key, text)` 一个调用即可发声。
- 🎲 **语音概率触发**：按配置概率向 LLM 注入语音提示，引导其偶尔用语音回复；
  支持超长用户消息自动抑制，控制合成消耗。
- 🛠️ **合成参数可调**：音频格式、采样率、语速、音量、最大字符数、超时、输出目录、发送方式全部可配置。
- 📤 **两种发送方式**：`base64`（内嵌数据，跨机器最稳）/ `file`（本地路径，需与协议端共享文件系统）。

> 音色的**训练**不在本插件范围内。请先在火山方舟控制台（或其他途径）完成声音复刻训练，
> 拿到 `S_` / `icl_` 音色 ID 后填入配置或调用时传入。

---

## 前置条件

1. 已部署 **NekroAgent**，并接入 **OneBot V11** 协议端（如 NapCat）。
2. **火山方舟 API Key**，且该 Key 已开通**声音复刻**资源（`seed-icl-2.0`）。
3. 已训练完成的声音复刻音色 ID（`S_` / `icl_` 开头）。

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
| `AUDIO_FORMAT` | `mp3` | 音频格式：`mp3` / `ogg_opus` / `pcm` |
| `SAMPLE_RATE` | `24000` | 采样率：8000 / 16000 / 22050 / 24000 / 32000 / 44100 / 48000 |
| `SPEECH_RATE` | `0` | 语速 [-50, 100]：100 = 2.0 倍速，-50 = 0.5 倍速 |
| `LOUDNESS_RATE` | `0` | 音量 [-50, 100]：100 = 2.0 倍音量，-50 = 0.5 倍音量 |
| `MAX_TEXT_LENGTH` | `300` | 单次最大合成字符数（超出截断） |
| `REQUEST_TIMEOUT` | `60` | 合成请求超时（秒） |
| `OUTPUT_DIR` | `./data/nekro_agent/plugins/doubao_tts_voice` | 音频输出目录（`file` 发送方式下使用） |
| `SEND_MODE` | `base64` | 发送方式：`base64`（推荐）/ `file` |

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

---

## 常见问题

**`requested resource not granted`**
该 API Key 未开通「声音复刻」资源（`seed-icl-2.0`）。到火山方舟控制台为对应 Key 开通声音复刻服务后重试。

**返回 401 / 鉴权失败**
检查 `API_KEY` 是否填写正确；若使用独立的复刻 Key，确认 `VOICE_CLONE_API_KEY` 配置。

**调用成功但群里没有语音**
- 确认 OneBot V11 协议端在线且支持发送 `record` 消息；
- 协议端（如 NapCat）需要可用的 ffmpeg 才能转码发送语音，请检查协议端日志；
- 默认 `base64` 发送方式兼容性最好；改用 `file` 时需保证 NekroAgent 与协议端共享文件系统路径。

**语音触发太频繁 / 从不触发**
调整 `VOICE_TRIGGER_PROBABILITY`（0~1）；同时注意 `VOICE_TRIGGER_MAX_INPUT_LENGTH` 的抑制逻辑，
长消息场景默认不发语音。

**音色 ID 从哪里获得**
在火山方舟控制台完成声音复刻训练后获得（`S_` / `icl_` 开头）。训练流程不属于本插件范围。

---

## 说明

- 仅适配 **onebot_v11** 适配器；其他适配器未做适配。
- 语音合成按量计费（火山方舟侧），请合理设置 `MAX_TEXT_LENGTH` 与触发概率控制消耗。
- 合成失败、发送失败均记录到 NekroAgent 日志（前缀含 `[chat_key]`），排查时先看日志。

## 版权

MIT
