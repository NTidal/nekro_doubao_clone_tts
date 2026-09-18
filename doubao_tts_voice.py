"""
# 豆包声音复刻语音插件(nekro_doubao_clone_tts)
# 火山方舟声音复刻（Voice Clone）语音合成

本插件仅提供「用已训练好的克隆音色合成语音并发送」的能力，通过 OneBot V11 发送语音消息。

## 声音复刻语音合成
使用事先训练好的 `S_`/`icl_` 克隆音色，通过通用 ICL 合成端点
`https://openspeech.bytedance.com/api/v3/tts/unidirectional` + `X-Api-Resource-Id: seed-icl-2.0`
合成语音，再作为 `record` 语音消息发送。
- 沙箱方法：`send_voice_clone(chat_key, text, speaker_id="")`
  （`speaker_id` 留空时使用配置项 `CLONE_DEFAULT_SPEAKER` 指定的默认音色（占位默认值，须替换为自己的音色），
  因此 LLM 只需调用 `send_voice_clone(chat_key, text)` 即可用已训练音色发声）

> 注：音色训练不在本插件范围内，请在火山方舟控制台（或其他途径）完成声音复刻训练，
> 得到 `S_`/`icl_` 音色 ID 后填入配置或调用时传入。
> 训练得到的音色要用 TTS 合成，需要该 API Key 已开通「声音复刻」资源
> （`seed-icl-2.0`），否则会报 `requested resource not granted`。

## 配置说明（关键）
| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| API_KEY | 空（必填） | 火山方舟 API Key（通用 Key，需开通声音复刻资源） |
| VOICE_CLONE_TTS_URL | https://openspeech.bytedance.com/api/v3/tts/unidirectional | 克隆音色合成地址（可改） |
| VOICE_CLONE_RESOURCE_ID | seed-icl-2.0 | 克隆音色合成资源 ID |
| VOICE_CLONE_API_KEY | 空（留空则复用 API_KEY） | 复刻专用 Key（如需独立） |
| CLONE_DEFAULT_SPEAKER | S_xxxxxxxx（占位） | 默认克隆音色 ID（S_/icl_ 开头），须替换为自己的音色 |
| AUDIO_FORMAT / SAMPLE_RATE / SPEECH_RATE / LOUDNESS_RATE | ... | 合成音频参数 |
| MAX_TEXT_LENGTH / REQUEST_TIMEOUT / OUTPUT_DIR / SEND_MODE | ... | 通用参数 |
| VOICE_TRIGGER_PROBABILITY / VOICE_TRIGGER_PROMPT / VOICE_TRIGGER_MAX_INPUT_LENGTH | ... | 语音概率触发（提示注入） |
| VOICE_COOLDOWN | 60 | 语音冷却秒数：冷却期内不进行触发概率计算，并拒绝 LLM 的语音请求；0 表示不启用 |
| VOICE_DEDUP_WINDOW | 300 | 内容防抖窗口秒数：窗口内与上一条语音内容高度相似的请求会被拒绝；0 表示不启用 |
| VOICE_DEDUP_SIMILARITY | 0.6 | 内容防抖相似度阈值（0~1）：规范化后与上一条语音的相似度达到该值即判定为重复 |
"""

import base64
import json
import pathlib
import random
import re
import time
import uuid
from difflib import SequenceMatcher
from typing import Literal

import httpx
from pydantic import Field

from nekro_agent.adapters.onebot_v11.core.bot import get_bot
from nekro_agent.api import core, i18n
from nekro_agent.api.plugin import (
    ConfigBase,
    ExtraField,
    NekroPlugin,
    SandboxMethodType,
)
from nekro_agent.api.schemas import AgentCtx
from nekro_agent.models.db_chat_channel import DBChatChannel
from nekro_agent.schemas.chat_message import ChatMessage, ChatType
from nekro_agent.schemas.signal import MsgSignal

# 默认端点（可通过配置覆盖）
DEFAULT_VOICE_CLONE_TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"

plugin = NekroPlugin(
    name="豆包声音复刻语音插件",
    module_name="doubao_tts_voice",
    description="火山方舟声音复刻（Voice Clone）语音合成，用已训练的克隆音色把文本合成为语音并经 OneBot V11 发送",
    version="1.0",
    author="NTidal",
    url="https://github.com/NTidal/nekro_doubao_clone_tts",
    support_adapter=["onebot_v11"],
    i18n_name=i18n.i18n_text(
        zh_CN="豆包声音复刻语音插件",
        en_US="Doubao Voice Clone Plugin",
    ),
    i18n_description=i18n.i18n_text(
        zh_CN="声音复刻语音合成，用已训练的克隆音色经 OneBot V11 发送语音",
        en_US="Voice clone TTS via OneBot V11 using a pre-trained cloned voice",
    ),
    allow_sleep=False,
    sleep_brief="用于声音复刻语音合成，仅在需要用克隆音色发送语音时激活。",
)


@plugin.mount_config()
class DoubaoVoiceConfig(ConfigBase):
    """豆包声音复刻语音配置"""

    API_KEY: str = Field(
        default="",
        title="API Key",
        description="火山方舟 API Key（通用 Key，需已开通声音复刻资源 seed-icl-2.0），必填",
        json_schema_extra=ExtraField(
            is_secret=True,
            required=True,
            i18n_title=i18n.i18n_text(zh_CN="API Key", en_US="API Key"),
            i18n_description=i18n.i18n_text(
                zh_CN="火山方舟 API Key（通用 Key，需已开通声音复刻资源 seed-icl-2.0），必填",
                en_US="Volcengine Ark API Key with voice clone (seed-icl-2.0) resource granted, required",
            ),
        ).model_dump(),
    )
    # ---- 声音复刻合成 ----
    VOICE_CLONE_TTS_URL: str = Field(
        default=DEFAULT_VOICE_CLONE_TTS_URL,
        title="克隆音色合成地址 (POST)",
        description="用克隆音色（S_/icl_）合成的接口地址，可修改，默认已预填",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="克隆音色合成地址 (POST)", en_US="Voice Clone TTS URL (POST)"),
            i18n_description=i18n.i18n_text(
                zh_CN="用克隆音色（S_/icl_）合成的接口地址，可修改，默认已预填",
                en_US="TTS endpoint for cloned voices, configurable with default prefilled",
            ),
        ).model_dump(),
    )
    VOICE_CLONE_RESOURCE_ID: str = Field(
        default="seed-icl-2.0",
        title="克隆音色合成资源 ID",
        description="复刻音色合成资源 ID（seed-icl-2.0）",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="克隆音色合成资源 ID", en_US="Voice Clone Resource ID"),
        ).model_dump(),
    )
    VOICE_CLONE_API_KEY: str = Field(
        default="",
        title="复刻专用 API Key",
        description="声音复刻专用 API Key，留空则复用上方 API_KEY",
        json_schema_extra=ExtraField(
            is_secret=True,
            i18n_title=i18n.i18n_text(zh_CN="复刻专用 API Key", en_US="Voice Clone API Key"),
            i18n_description=i18n.i18n_text(
                zh_CN="声音复刻专用 API Key，留空则复用上方 API_KEY",
                en_US="Dedicated key for voice clone; empty to reuse API_KEY",
            ),
        ).model_dump(),
    )
    CLONE_DEFAULT_SPEAKER: str = Field(
        default="S_xxxxxxxx",
        title="默认克隆音色 ID",
        description="调用 send_voice_clone 时不传 speaker_id 时使用的默认克隆音色（S_/icl_ 开头），须替换为自己在火山方舟训练得到的音色",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="默认克隆音色 ID", en_US="Default Clone Speaker ID"),
            i18n_description=i18n.i18n_text(
                zh_CN="send_voice_clone 不传 speaker_id 时使用的默认克隆音色，须替换为自己的音色",
                en_US="Default clone speaker used when send_voice_clone omits speaker_id; replace with your own voice",
            ),
        ).model_dump(),
    )
    # ---- 语音概率触发（提示注入）----
    VOICE_TRIGGER_PROBABILITY: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        title="语音触发概率",
        description="每次对话以该概率向 LLM 注入语音提示，引导其用克隆音色语音回复（0~1）",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="语音触发概率", en_US="Voice Trigger Probability"),
            i18n_description=i18n.i18n_text(
                zh_CN="每次对话以该概率提示 LLM 用克隆音色语音回复",
                en_US="Probability per turn to prompt the LLM to reply with a cloned voice",
            ),
        ).model_dump(),
    )
    VOICE_TRIGGER_PROMPT: str = Field(
        default="本条回复请用语音发出（调用 send_voice_clone，第一个参数为 chat_key，第二个参数为要说的口语内容，内容自然口语化、不宜过长）。",
        title="语音触发提示词",
        description="命中概率时注入给 LLM 的语音提示文本（措辞可自定义）",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="语音触发提示词", en_US="Voice Trigger Prompt"),
            i18n_description=i18n.i18n_text(
                zh_CN="命中概率时注入给 LLM 的语音提示文本，可自定义措辞",
                en_US="Prompt text injected when probability is hit; wording customizable",
            ),
        ).model_dump(),
    )
    VOICE_TRIGGER_MAX_INPUT_LENGTH: int = Field(
        default=100,
        ge=0,
        title="语音触发最大输入长度",
        description="当本条用户消息文本长度超过该值时不触发语音（防长消息高消耗）；0 表示不限制",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="语音触发最大输入长度", en_US="Voice Trigger Max Input Length"),
            i18n_description=i18n.i18n_text(
                zh_CN="用户消息超过该长度则不触发语音，防止长消息造成高消耗；0=不限",
                en_US="Suppress voice when user message exceeds this length to avoid cost; 0=unlimited",
            ),
        ).model_dump(),
    )
    VOICE_COOLDOWN: int = Field(
        default=60,
        ge=0,
        title="语音冷却（秒）",
        description="发送语音后进入冷却：冷却期内不进行触发概率计算（不注入语音提示），并拒绝 LLM 的语音请求；0 表示不启用冷却",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="语音冷却（秒）", en_US="Voice Cooldown (seconds)"),
            i18n_description=i18n.i18n_text(
                zh_CN="发送语音后进入冷却：冷却期内不进行概率触发计算，LLM 的语音请求也会被拒绝；0=不启用",
                en_US="After a voice is sent, probability triggering is suspended and LLM voice requests are rejected during the cooldown; 0=disabled",
            ),
        ).model_dump(),
    )
    VOICE_DEDUP_WINDOW: int = Field(
        default=300,
        ge=0,
        title="内容防抖窗口（秒）",
        description="该窗口内与上一条语音内容高度相似的合成请求会被拒绝（防 LLM 流式输出连发两条相近语音）；0 表示不启用内容防抖",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="内容防抖窗口（秒）", en_US="Voice Dedup Window (seconds)"),
            i18n_description=i18n.i18n_text(
                zh_CN="窗口内与上一条语音内容高度相似的请求会被拒绝；0=不启用",
                en_US="Requests too similar to the previous voice within this window are rejected; 0=disabled",
            ),
        ).model_dump(),
    )
    VOICE_DEDUP_SIMILARITY: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        title="内容防抖相似度阈值",
        description="文本规范化（去标点/空白、转小写）后与上一条语音的相似度达到该值即判定为重复并拒绝",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="内容防抖相似度阈值", en_US="Voice Dedup Similarity Threshold"),
            i18n_description=i18n.i18n_text(
                zh_CN="规范化后与上一条语音相似度达到该值即拒绝；0~1，越低越严格",
                en_US="Reject when normalized similarity with the previous voice reaches this ratio; 0~1, lower is stricter",
            ),
        ).model_dump(),
    )
    # ---- 合成音频参数 ----
    AUDIO_FORMAT: Literal["mp3", "ogg_opus", "pcm"] = Field(
        default="mp3",
        title="音频格式",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="音频格式", en_US="Audio Format"),
        ).model_dump(),
    )
    SAMPLE_RATE: int = Field(
        default=24000,
        title="采样率",
        description="可选 [8000,16000,22050,24000,32000,44100,48000]",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="采样率", en_US="Sample Rate"),
        ).model_dump(),
    )
    SPEECH_RATE: int = Field(
        default=0,
        ge=-50,
        le=100,
        title="语速",
        description="[-50,100]，100=2.0 倍速，-50=0.5 倍速",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="语速", en_US="Speech Rate"),
        ).model_dump(),
    )
    LOUDNESS_RATE: int = Field(
        default=0,
        ge=-50,
        le=100,
        title="音量",
        description="[-50,100]，100=2.0 倍音量，-50=0.5 倍音量",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="音量", en_US="Loudness Rate"),
        ).model_dump(),
    )
    MAX_TEXT_LENGTH: int = Field(
        default=300,
        ge=1,
        le=5000,
        title="最大合成字符数",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="最大合成字符数", en_US="Max Text Length"),
        ).model_dump(),
    )
    REQUEST_TIMEOUT: int = Field(
        default=60,
        ge=5,
        title="请求超时（秒）",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="请求超时（秒）", en_US="Request Timeout (s)"),
        ).model_dump(),
    )
    OUTPUT_DIR: str = Field(
        default="./data/nekro_agent/plugins/doubao_tts_voice",
        title="音频输出目录",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="音频输出目录", en_US="Output Directory"),
        ).model_dump(),
    )
    SEND_MODE: Literal["base64", "file"] = Field(
        default="base64",
        title="发送方式",
        description="base64: 内嵌音频数据，跨机器最稳；file: 使用本地文件路径（需与协议端共享文件系统）",
        json_schema_extra=ExtraField(
            i18n_title=i18n.i18n_text(zh_CN="发送方式", en_US="Send Mode"),
            i18n_description=i18n.i18n_text(
                zh_CN="base64 内嵌数据最稳；file 使用本地路径需与协议端共享文件系统",
                en_US="base64 is most robust; file mode requires shared filesystem",
            ),
        ).model_dump(),
    )


config: DoubaoVoiceConfig = plugin.get_config(DoubaoVoiceConfig)


def _clone_api_key() -> str:
    """复刻专用 Key，为空则复用主 Key。"""
    return config.VOICE_CLONE_API_KEY or config.API_KEY


async def _synthesize_unidirectional(
    url: str,
    resource_id: str,
    api_key: str,
    text: str,
    speaker: str,
) -> bytes:
    """通用 HTTP 单向流式语音合成，解析逐行 JSON 并拼接 base64 音频。"""
    if len(text) > config.MAX_TEXT_LENGTH:
        text = text[: config.MAX_TEXT_LENGTH]

    audio_params: dict = {"format": config.AUDIO_FORMAT, "sample_rate": config.SAMPLE_RATE}
    if config.SPEECH_RATE:
        audio_params["speech_rate"] = config.SPEECH_RATE
    if config.LOUDNESS_RATE:
        audio_params["loudness_rate"] = config.LOUDNESS_RATE

    payload = {
        "user": {"uid": "nekro_agent"},
        "req_params": {
            "text": text,
            "speaker": speaker,
            "audio_params": audio_params,
        },
    }

    headers = {
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": resource_id,
        "X-Api-Request-Id": str(uuid.uuid4()),
    }

    audio = bytearray()
    try:
        async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    raise RuntimeError(f"语音合成接口返回状态码 {resp.status_code}: {(await resp.aread())[:300]}")
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    data = obj.get("data")
                    if data:
                        audio.extend(base64.b64decode(data))
                    else:
                        code = obj.get("code", 0)
                        if code not in (0, 20000000):
                            raise RuntimeError(f"语音合成失败: code={code}, message={obj.get('message', '')}")
    except httpx.HTTPError as e:
        raise RuntimeError(f"请求语音合成接口失败: {e}") from e

    if not audio:
        raise RuntimeError("语音合成返回音频为空")
    return bytes(audio)


async def _synthesize_voice_clone(text: str, speaker_id: str) -> bytes:
    """用克隆音色（S_/icl_）合成（ICL 资源）。"""
    key = _clone_api_key()
    if not key:
        raise RuntimeError("未配置 API_KEY / VOICE_CLONE_API_KEY")
    return await _synthesize_unidirectional(
        config.VOICE_CLONE_TTS_URL, config.VOICE_CLONE_RESOURCE_ID, key, text, speaker_id
    )


async def _send_voice_record(chat_key: str, audio_bytes: bytes, ext: str = "") -> None:
    """将音频作为 OneBot V11 语音（record）发送到群聊或私聊。"""
    from nonebot.adapters.onebot.v11 import MessageSegment

    db_chat_channel: DBChatChannel = await DBChatChannel.get_channel(chat_key=chat_key)
    chat_type = db_chat_channel.chat_type
    chat_id = db_chat_channel.channel_id  # 形如 "group_123456" / "private_123456"

    ext = ext or config.AUDIO_FORMAT
    file_path: str | None = None
    if config.SEND_MODE == "file":
        out_dir = pathlib.Path(config.OUTPUT_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        file_path = str(out_dir / f"voice_{chat_id.replace('/', '_')}_{int(time.time() * 1000)}.{ext}")
        pathlib.Path(file_path).write_bytes(audio_bytes)

    record_file = f"file://{file_path}" if config.SEND_MODE == "file" else "base64://" + base64.b64encode(audio_bytes).decode()
    segment = MessageSegment.record(file=record_file)

    if chat_type == ChatType.GROUP:
        group_id = int(chat_id.split("_")[1])
        await get_bot().call_api("send_group_msg", group_id=group_id, message=[segment])
    elif chat_type == ChatType.PRIVATE:
        user_id = int(chat_id.split("_")[1])
        await get_bot().call_api("send_private_msg", user_id=user_id, message=[segment])
    else:
        raise RuntimeError(f"不支持的会话类型: {chat_type}")


# ==================== 语音冷却 ====================

# 记录每个频道最近一次语音发送的时间戳，供冷却判断使用：{chat_key: 时间戳}
_last_voice_time: dict[str, float] = {}


def _voice_in_cooldown(chat_key: str) -> bool:
    """该频道是否处于语音冷却期内。VOICE_COOLDOWN<=0 表示不启用冷却。"""
    cooldown = max(0, int(config.VOICE_COOLDOWN))
    if cooldown <= 0:
        return False
    last = _last_voice_time.get(chat_key, 0.0)
    return (time.time() - last) < cooldown


def _voice_cooldown_remaining(chat_key: str) -> int:
    """返回剩余冷却秒数（向上取整）；未在冷却中返回 0。"""
    cooldown = max(0, int(config.VOICE_COOLDOWN))
    if cooldown <= 0:
        return 0
    remaining = cooldown - (time.time() - _last_voice_time.get(chat_key, 0.0))
    return max(0, int(remaining) + (1 if remaining % 1 else 0))


# ==================== 内容防抖 ====================

# 记录每个频道上一条已发送语音的（规范化文本, 时间戳），供内容防抖使用
_last_voice_text: dict[str, tuple[str, float]] = {}

# 规范化时剔除的字符：标点、空白、常见装饰符号
_DEDUP_STRIP_RE = re.compile(r"[\s，。？！、~…·,.!?\-—:：;；「」『』“”\"'（）()@＠\[\]{}<>《》]+")
# 叠词/语气后缀，对相似度判定贡献极小，规范化时剔除
_DEDUP_TAIL_RE = re.compile(r"(呀|啊|啦|咯|哟|呦|喔|哦|呢|吗|吧|哈|呗|嘞|酶|捏|喵|滴|的说|一下)+$")


def _normalize_for_dedup(text: str) -> str:
    """文本规范化：剔除标点/空白/装饰符号、去叠词语气尾、转小写，仅保留对内容有区分度的部分。"""
    t = _DEDUP_STRIP_RE.sub("", text)
    t = _DEDUP_TAIL_RE.sub("", t)
    return t.lower()


def _is_duplicated_content(chat_key: str, text: str) -> tuple[bool, float]:
    """判断是否与窗口内的上一条语音内容高度相似。

    返回 (是否重复, 相似度)。VOICE_DEDUP_WINDOW<=0 时不启用，恒为 False。
    """
    window = max(0, int(config.VOICE_DEDUP_WINDOW))
    if window <= 0:
        return False, 0.0
    record = _last_voice_text.get(chat_key)
    if not record:
        return False, 0.0
    last_norm, ts = record
    if not last_norm or (time.time() - ts) >= window:
        return False, 0.0
    new_norm = _normalize_for_dedup(text)
    if not new_norm or not last_norm:
        return False, 0.0
    # 短文本包含判定：一条是另一条的子串（含相等）视为重复，
    # 处理"流式输出先发半句、再发全句"这类场景（SequenceMatcher 对长短差异不敏感）
    if new_norm in last_norm or last_norm in new_norm:
        return True, 1.0
    ratio = SequenceMatcher(None, last_norm, new_norm).ratio()
    threshold = min(1.0, max(0.0, float(config.VOICE_DEDUP_SIMILARITY)))
    return ratio >= threshold, round(ratio, 3)


# ==================== 沙箱方法 ====================

@plugin.mount_sandbox_method(SandboxMethodType.TOOL, "发送克隆音色语音")
async def send_voice_clone(_ctx: AgentCtx, chat_key: str, text: str, speaker_id: str = "") -> bool:
    """使用已训练好的克隆音色把文本合成为语音并发送。

    不传 speaker_id 时使用配置项 CLONE_DEFAULT_SPEAKER 指定的默认克隆音色，
    LLM 只需调用 send_voice_clone(chat_key, text) 即可用已训练音色发声。
    语音冷却期（VOICE_COOLDOWN）内调用会被直接拒绝；与上一条语音内容高度相似
    的请求（VOICE_DEDUP_WINDOW/VOICE_DEDUP_SIMILARITY）也会被拒绝，请勿重复发送相近内容。

    Args:
        chat_key (str): 聊天的唯一标识符，形如 "onebot_v11-group_123456"
        text (str): 需要合成的语音文本
        speaker_id (str, optional): 克隆音色 ID（S_/icl_ 开头，需事先训练好），
            留空则使用配置项 CLONE_DEFAULT_SPEAKER

    Returns:
        bool: 操作是否成功
    """
    if _voice_in_cooldown(chat_key):
        core.logger.info(
            f"[{chat_key}] 语音冷却中（剩余 {_voice_cooldown_remaining(chat_key)} 秒），已拒绝本次语音请求"
        )
        return False
    speaker_id = (speaker_id or config.CLONE_DEFAULT_SPEAKER).strip()
    if not text or not text.strip() or not speaker_id:
        core.logger.error(f"[{chat_key}] 文本或克隆音色为空，已忽略")
        return False
    # 内容防抖：窗口内与上一条语音高度相似（含互为子串）则拒绝，防 LLM 流式输出连发相近语音
    dup, ratio = _is_duplicated_content(chat_key, text)
    if dup:
        core.logger.info(
            f"[{chat_key}] 内容防抖命中（相似度 {ratio}），已拒绝与上一条语音相近的请求: {text.strip()[:50]}"
        )
        return False
    try:
        audio_bytes = await _synthesize_voice_clone(text.strip(), speaker_id)
        await _send_voice_record(chat_key, audio_bytes)
    except Exception as e:
        core.logger.error(f"[{chat_key}] 克隆音色合成/发送失败: {e}")
        return False
    else:
        # 仅在语音实际发送成功后进入冷却并记录内容快照
        _last_voice_time[chat_key] = time.time()
        _last_voice_text[chat_key] = (_normalize_for_dedup(text.strip()), time.time())
        core.logger.info(f"[{chat_key}] 克隆音色 {speaker_id} 合成并发送成功 (内容: {text.strip()[:50]})")
        return True


# ==================== 语音概率触发（提示注入） ====================

# 记录每个频道最近一条用户消息的长度，供语音触发判断使用
_last_input_len: dict[str, int] = {}


@plugin.mount_on_user_message()
async def _record_input_len(_ctx: AgentCtx, message: ChatMessage) -> MsgSignal:
    """记录本条用户消息长度，用于'长消息不触发语音'的成本控制。"""
    _last_input_len[_ctx.chat_key] = len(message.content_text or "")
    return MsgSignal.CONTINUE


@plugin.mount_prompt_inject_method(
    name="语音概率触发",
    description="以配置的概率向 LLM 注入语音提示，引导其偶尔用克隆音色语音回复",
)
async def voice_trigger_inject(_ctx: AgentCtx) -> str:
    """按 VOICE_TRIGGER_PROBABILITY 概率返回语音提示；未命中、输入过长或冷却期内返回空串。"""
    if config.VOICE_TRIGGER_PROBABILITY <= 0:
        return ""
    # 冷却期内不进行触发概率计算，不注入语音提示
    if _voice_in_cooldown(_ctx.chat_key):
        return ""
    # 用户消息过长时不触发语音，防止长内容合成造成高消耗
    max_len = config.VOICE_TRIGGER_MAX_INPUT_LENGTH
    if max_len > 0 and _last_input_len.get(_ctx.chat_key, 0) > max_len:
        return ""
    if random.random() >= config.VOICE_TRIGGER_PROBABILITY:
        return ""
    return config.VOICE_TRIGGER_PROMPT


@plugin.mount_cleanup_method()
async def clean_up():
    """清理插件"""
