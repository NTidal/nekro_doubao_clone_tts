# 豆包声音复刻语音插件(nekro_doubao_clone_tts)
# 火山方舟声音复刻（Voice Clone）语音合成

本插件仅提供「用已训练好的克隆音色合成语音并发送」的能力，通过 OneBot V11 发送语音消息。

## 声音复刻语音合成
使用事先训练好的 `S_`/`icl_` 克隆音色，通过通用 ICL 合成端点
`https://openspeech.bytedance.com/api/v3/tts/unidirectional` + `X-Api-Resource-Id: seed-icl-2.0`
合成语音，再作为 `record` 语音消息发送。
- 沙箱方法：`send_voice_clone(chat_key, text, speaker_id="")`
  （`speaker_id` 留空时使用配置项 `CLONE_DEFAULT_SPEAKER` 指定的默认音色，如 `S_Fo3GZ6wc2`，
  因此 LLM 只需调用 `send_voice_clone(chat_key, text)` 即可用已训练音色发声）

> 注：音色训练不在本插件范围内，请在火山方舟控制台（或其他途径）完成声音复刻训练，
> 得到 `S_`/`icl_` 音色 ID 后填入配置或调用时传入。
> 训练得到的音色要用 TTS 合成，需要该 API Key 已开通「声音复刻」资源
> （`seed-icl-2.0`），否则会报 `requested resource not granted`。
