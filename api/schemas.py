from typing import Literal, Optional

from pydantic import BaseModel, Field

AudioResponseFormat = Literal["wav", "pcm", "opus"]


class SpeechRequest(BaseModel):
    # OpenAI-compatible core fields
    model: str = Field(default="openbmb/VoxCPM2")
    input: str
    voice: str = Field(default="alloy")
    response_format: AudioResponseFormat = Field(default="wav")
    speed: float = Field(default=1.0, ge=0.25, le=4.0)

    # VoxCPM extensions
    control_instruction: Optional[str] = None
    prompt_wav_path: Optional[str] = None
    prompt_text: Optional[str] = None
    cfg_value: float = Field(default=2.0, ge=1.0, le=5.0)
    inference_timesteps: int = Field(default=10, ge=1, le=60)
    denoise: bool = False
    normalize: bool = False


class VoiceCloneRequest(BaseModel):
    model: str = Field(default="openbmb/VoxCPM2")
    input: str
    voice: str = Field(default="alloy")
    response_format: AudioResponseFormat = Field(default="wav")
    speed: float = Field(default=1.0, ge=0.25, le=4.0)

    control_instruction: Optional[str] = None
    prompt_wav_path: Optional[str] = None
    prompt_text: Optional[str] = None
    cfg_value: float = Field(default=2.0, ge=1.0, le=5.0)
    inference_timesteps: int = Field(default=10, ge=1, le=60)
    denoise: bool = False
    normalize: bool = False


class VoiceLabelOut(BaseModel):
    key: str
    value: str


class VoiceStatOut(BaseModel):
    request_count: int
    total_audio_seconds: float
    last_used_at: Optional[str] = None


class VoiceOut(BaseModel):
    id: str
    database_id: int
    voice_id: str
    name: str
    description: str
    category: Optional[str] = None
    language: Optional[str] = None
    gender: Optional[str] = None
    file_name: str
    reference_wav_path: str
    relative_path: str
    enabled: bool
    owner: Optional[str] = None
    version: Optional[str] = None
    created_at: str
    updated_at: str
    labels: list[VoiceLabelOut] = Field(default_factory=list)
    stats: Optional[VoiceStatOut] = None
