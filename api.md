# VoxCPM API 调用说明

本文档说明 OpenClaw 或其他 HTTP 客户端如何调用 VoxCPM2 语音合成服务。

## 接口概览

| 接口 | 方法 | 用途 |
|---|---|---|
| `/health` | GET | 服务存活检查。 |
| `/v1/models` | GET | 列出允许调用的模型。 |
| `/v1/audio/voices` | GET | 列出本地音色参考音频。 |
| `/v1/voices` | GET | `/v1/audio/voices` 的别名。 |
| `/v1/audio/speech` | POST | 通用文本转语音入口，兼容 OpenAI 风格调用。 |
| `/v1/audio/voice_clone` | POST | 显式声音克隆入口，要求 `voice` 能解析到本地参考音频。 |
| `/v1/audio/clone` | POST | `/v1/audio/voice_clone` 的别名。 |

## 服务启动

默认启动：

```bash
python3 -m api
```

默认监听：

```text
http://0.0.0.0:8808
```

可通过环境变量覆盖：

```bash
HOST=127.0.0.1 PORT=8808 python3 -m api
```

可通过 `ALLOWED_MODELS` 配置允许加载的模型，多个模型使用英文逗号分隔：

```bash
ALLOWED_MODELS=openbmb/VoxCPM2,./pretrained_models/VoxCPM2 python3 -m api
```

本地音色参考目录由 `VOICE_REFERENCES_DIR` 指定，默认是：

```text
voices
```

voices 元数据使用 SQLite 保存。数据库路径由 `VOICES_DB_PATH` 指定，默认是：

```text
data/voices.sqlite
```

也可以通过 `DATABASE_URL` 指定完整 SQLAlchemy 数据库 URL：

```bash
DATABASE_URL=sqlite:////home/miaohf/Documents/mycode/VoxCPM/data/voices.sqlite python3 -m api
```

启动时同步到数据库的音色文件范围：

- 仅 `VOICE_REFERENCES_DIR` 根目录下的 `*.wav`（不递归子目录）。
- 子目录中的文件不会自动入库。

`prompt_wav_path` 仍允许在音色目录内使用以下后缀（若你手动放入对应文件）：

```text
.wav, .mp3, .flac, .m4a, .ogg
```

## 通用约定

### Base URL

```text
http://localhost:8808
```

### 请求格式

除 `/health`、`/v1/models`、`/v1/audio/voices` 外，生成接口均使用：

```http
Content-Type: application/json
```

### 响应音频格式

`response_format` 支持：

| 值 | 响应 Content-Type | 说明 |
|---|---|---|
| `wav` | `audio/wav` | 默认值，包含 WAV 头，客户端可直接保存和播放。 |
| `opus` | `audio/opus` | Opus 压缩音频，兼容 OpenAI `response_format=opus`；需要系统安装 `ffmpeg` 且支持 `libopus`。 |
| `pcm` | `application/octet-stream` | 裸 `int16` PCM 字节流，响应头会包含采样率、声道数、位深和编码方式。 |

OpenClaw 使用 `wav` 可直接保存为音频文件。

`pcm` 响应头：

| 响应头 | 说明 |
|---|---|
| `X-Sample-Rate` | 采样率，例如 `48000`。 |
| `X-Channels` | 声道数，当前为 `1`。 |
| `X-Sample-Width-Bits` | 采样位深，当前为 `16`。 |
| `X-PCM-Encoding` | PCM 编码，当前为 `signed-integer-little-endian`。 |

### 错误格式

API 业务错误和校验错误统一返回：

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message.",
    "retryable": false
  }
}
```

请求字段校验失败时会额外包含 `details`：

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed.",
    "retryable": false,
    "details": []
  }
}
```

## GET /health

健康检查。

### 请求

```bash
curl http://localhost:8808/health
```

### 响应

```json
{
  "status": "ok"
}
```

## GET /v1/models

列出模型。返回值来自 `ALLOWED_MODELS`，默认只有 `openbmb/VoxCPM2`。

### 请求

```bash
curl http://localhost:8808/v1/models
```

### 响应

```json
{
  "object": "list",
  "data": [
    {
      "id": "openbmb/VoxCPM2",
      "object": "model",
      "owned_by": "openbmb"
    }
  ]
}
```

## GET /v1/audio/voices

列出可用于克隆的本地参考音色。

别名：

```text
GET /v1/voices
```

### 请求

```bash
curl http://localhost:8808/v1/audio/voices
```

支持查询参数（可组合）：

| 参数 | 类型 | 说明 |
|---|---|---|
| `accent` | string | 按口音/风格关键词过滤（会匹配 `category`、`description` 以及标签中的 `accent/tone/style/role_hint/voice_display_name`）。 |
| `gender` | string | 按性别关键词过滤（会匹配 `gender` 字段和标签中的 `gender/sex`）。 |
| `lang` | string | 按语言过滤，支持 `zh`/`en` 以及 `中文`/`英文`/`chinese`/`english` 等别名。 |

查询示例：

```bash
# 中文女声
curl "http://localhost:8808/v1/audio/voices?lang=zh&gender=female"

# 英文音色
curl "http://localhost:8808/v1/audio/voices?lang=en"

# 带英式口音关键词（示例）
curl "http://localhost:8808/v1/audio/voices?accent=british"
```

### 响应字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `object` | string | 固定为 `list`。 |
| `data` | array | 音色列表。 |
| `voices_dir` | string | 实际扫描的音色目录绝对路径。 |

每个音色对象：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 等同于 `voice_id`，可作为 `voice` 传入。 |
| `database_id` | integer | SQLite 自增主键。 |
| `voice_id` | string | 稳定音色 ID，可作为 `voice` 传入。 |
| `name` | string | 显示名，也可作为 `voice` 传入。 |
| `description` | string | 音色描述。 |
| `category` | string 或 null | 音色分类。 |
| `language` | string 或 null | 语言。 |
| `gender` | string 或 null | 性别。 |
| `file_name` | string | 相对 `VOICE_REFERENCES_DIR` 的音频文件路径。 |
| `reference_wav_path` | string | 服务端参考音频绝对路径。 |
| `relative_path` | string | 相对 `voices_dir` 的路径，也可作为 `voice` 传入。 |
| `enabled` | boolean | 是否启用。 |
| `owner` | string 或 null | 所有者。 |
| `version` | string 或 null | 版本。 |
| `created_at` | string | 创建时间。 |
| `updated_at` | string | 更新时间。 |
| `labels` | array | 标签列表，每项包含 `key` 和 `value`。 |
| `stats` | object 或 null | 使用统计，包含 `request_count`、`total_audio_seconds`、`last_used_at`。 |

### 响应示例

```json
{
  "object": "list",
  "data": [
    {
      "id": "speaker_a",
      "database_id": 1,
      "voice_id": "speaker_a",
      "name": "speaker a",
      "description": "",
      "category": null,
      "language": null,
      "gender": null,
      "file_name": "speaker_a.wav",
      "reference_wav_path": "/path/to/voices/speaker_a.wav",
      "relative_path": "speaker_a.wav",
      "enabled": true,
      "owner": null,
      "version": null,
      "created_at": "2026-05-07T15:00:00+00:00",
      "updated_at": "2026-05-07T15:00:00+00:00",
      "labels": [],
      "stats": {
        "request_count": 0,
        "total_audio_seconds": 0.0,
        "last_used_at": null
      }
    }
  ],
  "voices_dir": "/path/to/voices"
}
```

## GET /v1/audio/voices/{voice_id}/download

按 `voice_id` 下载对应参考音频文件（二进制流）。

别名：

```text
GET /v1/voices/{voice_id}/download
```

### 请求示例

```bash
curl "http://localhost:8808/v1/audio/voices/Churcher/download" -o Churcher.wav
```

### 成功响应

```http
HTTP/1.1 200 OK
Content-Type: audio/wav
```

### 错误响应

voice 不存在：

```json
{
  "error": {
    "code": "VOICE_NOT_FOUND",
    "message": "`voice_id` 'foo' not found. Call `/v1/audio/voices` to list available voices.",
    "retryable": false
  }
}
```

音频文件不存在：

```json
{
  "error": {
    "code": "VOICE_AUDIO_NOT_FOUND",
    "message": "Audio file for voice 'foo' was not found: foo.wav",
    "retryable": false
  }
}
```

## POST /v1/audio/speech

通用语音合成接口，可作为 OpenClaw 默认调用入口。

它支持三种用法：

- 普通 TTS：只传 `input`。
- 音色设计：传 `control_instruction`，不需要本地参考音频。
- 参考音色合成：传 `voice`，如果能在 `/v1/audio/voices` 中匹配到本地音频，则作为 `reference_wav_path` 使用；匹配不到时不会报错，会退化为无参考音频生成。

### 请求字段

| 字段 | 类型 | 必填 | 默认值 | 约束 | 说明 |
|---|---|---:|---|---|---|
| `model` | string | 否 | `openbmb/VoxCPM2` | 必须在 `ALLOWED_MODELS` 中 | 模型 ID 或本地模型路径。 |
| `input` | string | 是 | - | 非空 | 要合成的文本。 |
| `voice` | string | 否 | `alloy` | - | OpenAI 兼容字段；若匹配本地音色，则使用对应参考音频。 |
| `response_format` | string | 否 | `wav` | `wav`、`opus` 或 `pcm` | 输出音频格式。 |
| `speed` | number | 否 | `1.0` | `0.25` 到 `4.0` | 仅兼容接收，不实际生效。 |
| `control_instruction` | string | 否 | `null` | - | VoxCPM 音色/风格控制指令，会被拼接为 `(<control>)<input>`。 |
| `prompt_wav_path` | string | 否 | `null` | 必须位于 `VOICE_REFERENCES_DIR` 内 | 极致克隆提示音频路径，可传绝对路径或相对音色目录的相对路径。 |
| `prompt_text` | string | 否 | `null` | - | `prompt_wav_path` 对应的准确转录文本。 |
| `cfg_value` | number | 否 | `2.0` | `1.0` 到 `5.0` | 生成引导强度。 |
| `inference_timesteps` | integer | 否 | `10` | `1` 到 `60` | 扩散推理步数，越高通常越慢。 |
| `denoise` | boolean | 否 | `false` | - | 是否启用去噪。 |
| `normalize` | boolean | 否 | `false` | - | 是否归一化音频。 |

### 最小请求

```bash
curl http://localhost:8808/v1/audio/speech \
  -H "Content-Type: application/json" \
  -o output.wav \
  -d '{
    "model": "openbmb/VoxCPM2",
    "input": "你好，我是 VoxCPM2 语音合成服务。",
    "voice": "alloy",
    "response_format": "wav"
  }'
```

### 音色设计请求

```bash
curl http://localhost:8808/v1/audio/speech \
  -H "Content-Type: application/json" \
  -o output.wav \
  -d '{
    "input": "欢迎使用 OpenClaw 调用 VoxCPM。",
    "control_instruction": "年轻女声，温暖自然，语速适中",
    "response_format": "wav",
    "cfg_value": 2.0,
    "inference_timesteps": 10
  }'
```

### 使用已登记音色

先获取音色：

```bash
curl http://localhost:8808/v1/audio/voices
```

再把返回的 `id`、`name` 或 `relative_path` 填入 `voice`：

```bash
curl http://localhost:8808/v1/audio/speech \
  -H "Content-Type: application/json" \
  -o cloned.wav \
  -d '{
    "input": "这句话会尽量使用指定参考音色来合成。",
    "voice": "speaker_a",
    "response_format": "wav"
  }'
```

### 成功响应

成功时直接返回二进制音频数据。

```http
HTTP/1.1 200 OK
Content-Type: audio/wav
```

`response_format=opus` 时：

```http
HTTP/1.1 200 OK
Content-Type: audio/opus
```

`response_format=pcm` 时：

```http
HTTP/1.1 200 OK
Content-Type: application/octet-stream
X-Sample-Rate: 48000
X-Channels: 1
X-Sample-Width-Bits: 16
X-PCM-Encoding: signed-integer-little-endian
```

### 错误响应

空文本：

```json
{
  "error": {
    "code": "EMPTY_INPUT",
    "message": "`input` must be a non-empty string.",
    "retryable": false
  }
}
```

生成失败：

```json
{
  "error": {
    "code": "TTS_GENERATION_FAILED",
    "message": "TTS generation failed: <error message>",
    "retryable": true
  }
}
```

模型不在白名单：

```json
{
  "error": {
    "code": "MODEL_NOT_ALLOWED",
    "message": "`model` 'other-model' is not allowed. Allowed models: openbmb/VoxCPM2.",
    "retryable": false
  }
}
```

提示音频路径不被允许：

```json
{
  "error": {
    "code": "PROMPT_AUDIO_PATH_NOT_ALLOWED",
    "message": "`prompt_wav_path` must point to an audio file under VOICE_REFERENCES_DIR.",
    "retryable": false
  }
}
```

## POST /v1/audio/voice_clone

显式声音克隆接口。它要求 `voice` 必须能在本地音色目录中匹配到参考音频，否则返回 400。

别名：

```text
POST /v1/audio/clone
```

适合 OpenClaw 在用户明确要求“使用某个已登记声音克隆”时调用。

### 请求字段

字段与 `/v1/audio/speech` 基本一致，区别如下：

| 字段 | 行为 |
|---|---|
| `voice` | 必须匹配 `/v1/audio/voices` 返回的 `id`、`name` 或 `relative_path`。 |
| `prompt_wav_path` | 可选；如果提供，必须位于 `VOICE_REFERENCES_DIR` 内。 |
| `prompt_text` | 如果提供了 `prompt_text` 但没有提供 `prompt_wav_path`，服务会自动使用该 `voice` 对应的参考音频作为 `prompt_wav_path`。 |

### 请求示例

```bash
curl http://localhost:8808/v1/audio/voice_clone \
  -H "Content-Type: application/json" \
  -o clone.wav \
  -d '{
    "input": "这是一段使用指定音色克隆生成的语音。",
    "voice": "speaker_a",
    "response_format": "wav",
    "control_instruction": "自然、清晰、略带微笑",
    "cfg_value": 2.0,
    "inference_timesteps": 10
  }'
```

### 极致克隆示例

```bash
curl http://localhost:8808/v1/audio/voice_clone \
  -H "Content-Type: application/json" \
  -o ultimate_clone.wav \
  -d '{
    "input": "现在开始生成新的内容。",
    "voice": "speaker_a",
    "prompt_text": "参考音频中实际说出的完整文本。",
    "response_format": "wav"
  }'
```

如果需要显式指定提示音频：

```json
{
  "input": "现在开始生成新的内容。",
  "voice": "speaker_a",
  "prompt_wav_path": "speaker_a.wav",
  "prompt_text": "参考音频中实际说出的完整文本。",
  "response_format": "wav"
}
```

### 错误响应

找不到音色：

```json
{
  "error": {
    "code": "VOICE_NOT_FOUND",
    "message": "`voice` 'speaker_a' not found. Call `/v1/audio/voices` to list available voices.",
    "retryable": false
  }
}
```

生成失败：

```json
{
  "error": {
    "code": "VOICE_CLONE_FAILED",
    "message": "Voice clone failed: <error message>",
    "retryable": true
  }
}
```

## OpenClaw 工具定义

将 VoxCPM 注册为 `text_to_speech` 工具：

```json
{
  "name": "voxcpm_text_to_speech",
  "description": "Call VoxCPM2 to synthesize speech from text. Use wav output by default.",
  "method": "POST",
  "url": "http://localhost:8808/v1/audio/speech",
  "headers": {
    "Content-Type": "application/json"
  },
  "body": {
    "model": "openbmb/VoxCPM2",
    "input": "{{text}}",
    "voice": "{{voice}}",
    "response_format": "wav",
    "control_instruction": "{{control_instruction}}",
    "cfg_value": 2.0,
    "inference_timesteps": 10,
    "denoise": false,
    "normalize": false
  },
  "response": {
    "type": "binary",
    "content_type": "audio/wav",
    "save_as": "{{output_path}}"
  }
}
```

如需查询可用音色，注册 `list_voices` 工具：

```json
{
  "name": "voxcpm_list_voices",
  "description": "List available local reference voices for VoxCPM voice cloning.",
  "method": "GET",
  "url": "http://localhost:8808/v1/audio/voices",
  "response": {
    "type": "json"
  }
}
```

显式克隆工具：

```json
{
  "name": "voxcpm_voice_clone",
  "description": "Synthesize speech using a registered local reference voice. The voice must exist in /v1/audio/voices.",
  "method": "POST",
  "url": "http://localhost:8808/v1/audio/voice_clone",
  "headers": {
    "Content-Type": "application/json"
  },
  "body": {
    "model": "openbmb/VoxCPM2",
    "input": "{{text}}",
    "voice": "{{voice}}",
    "response_format": "wav",
    "control_instruction": "{{control_instruction}}",
    "prompt_text": "{{prompt_text}}",
    "cfg_value": 2.0,
    "inference_timesteps": 10
  },
  "response": {
    "type": "binary",
    "content_type": "audio/wav",
    "save_as": "{{output_path}}"
  }
}
```

## OpenClaw 调用规则

按以下规则选择接口：

1. 用户只给文本，希望朗读：调用 `/v1/audio/speech`，只传 `input` 和 `response_format=wav`。
2. 用户描述想要的声音、情绪或语气：调用 `/v1/audio/speech`，把声音描述放到 `control_instruction`。
3. 用户指定某个已有音色：先调用 `/v1/audio/voices` 确认音色存在，再调用 `/v1/audio/voice_clone`。
4. 用户提供参考音频转录文本并追求最高相似度：调用 `/v1/audio/voice_clone`，传 `voice` 和 `prompt_text`。
5. 除非下游明确要求裸 PCM，否则始终使用 `response_format=wav`。

## 调用注意事项

- 首次调用模型加载较慢，OpenClaw 可以在启动后先调用一次短文本进行预热。
- 生成长文本时在 OpenClaw 侧分段合成，再拼接音频，避免单次请求过长导致推理时间和显存压力过高。
- `control_instruction` 中不要包含外层括号，服务端会自动拼接。
- `speed` 参数仅用于兼容 OpenAI 风格请求，不改变实际语速。
- `model` 必须在 `ALLOWED_MODELS` 中。
- `prompt_wav_path` 必须位于 `VOICE_REFERENCES_DIR` 内。
