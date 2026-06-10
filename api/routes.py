import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from api.audio import audio_duration_seconds, audio_response
from api.config import get_allowed_models, get_voices_dir
from api.database import get_db
from api.errors import api_error
from api.model_manager import clear_cuda_cache, generation_lock, get_model
from api.schemas import SpeechRequest, VoiceCloneRequest
from api.voices import (
    list_enabled_voices,
    get_voice_audio_file_path,
    record_voice_usage,
    resolve_prompt_wav_path,
    resolve_voice_by_id,
    resolve_voice_reference_path,
    voice_to_output,
)

router = APIRouter()
logger = logging.getLogger("voxcpm.api")


def _final_text(text: str, control_instruction: str | None) -> str:
    control = (control_instruction or "").strip()
    control = re.sub(r"[()（）]", "", control).strip()
    return f"({control}){text}" if control else text


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/v1/models")
def list_models() -> dict:
    return {
        "object": "list",
        "data": [
            {
                "id": model_id,
                "object": "model",
                "owned_by": model_id.split("/", 1)[0] if "/" in model_id else "local",
            }
            for model_id in get_allowed_models()
        ],
    }


@router.get("/v1/audio/voices")
@router.get("/v1/voices")
def list_voices(
    accent: str | None = Query(default=None, description="Filter by accent/style keyword."),
    gender: str | None = Query(default=None, description="Filter by gender keyword."),
    lang: str | None = Query(
        default=None,
        description="Filter by language. Supports zh/en/chinese/english/中文/英文.",
    ),
    db: Session = Depends(get_db),
) -> dict:
    voices = []
    for voice in list_enabled_voices(db, accent=accent, gender=gender, lang=lang):
        output = voice_to_output(voice)
        voices.append(output.model_dump() if hasattr(output, "model_dump") else output.dict())
    return {"object": "list", "data": voices, "voices_dir": str(get_voices_dir())}


@router.get("/v1/audio/voices/{voice_id}/download")
@router.get("/v1/voices/{voice_id}/download")
def download_voice_audio(voice_id: str, db: Session = Depends(get_db)):
    voice = resolve_voice_by_id(db, voice_id)
    if voice is None:
        raise api_error(
            404,
            "VOICE_NOT_FOUND",
            f"`voice_id` '{voice_id}' not found. Call `/v1/audio/voices` to list available voices.",
        )

    audio_path = get_voice_audio_file_path(voice)
    if not audio_path.is_file():
        raise api_error(
            404,
            "VOICE_AUDIO_NOT_FOUND",
            f"Audio file for voice '{voice_id}' was not found: {voice.file_name}",
        )

    return FileResponse(
        path=str(audio_path),
        media_type="audio/wav",
        filename=audio_path.name,
    )


@router.post("/v1/audio/speech")
def create_speech(req: SpeechRequest, db: Session = Depends(get_db)):
    text = (req.input or "").strip()
    if not text:
        raise api_error(400, "EMPTY_INPUT", "`input` must be a non-empty string.")

    try:
        model = get_model(req.model)
        resolved_reference_wav_path, resolved_voice_id = resolve_voice_reference_path(db, req.voice)
        prompt_wav_path = resolve_prompt_wav_path(req.prompt_wav_path)

        with generation_lock():
            try:
                wav = model.generate(
                    text=_final_text(text, req.control_instruction),
                    prompt_wav_path=prompt_wav_path,
                    prompt_text=req.prompt_text,
                    reference_wav_path=resolved_reference_wav_path,
                    cfg_value=req.cfg_value,
                    inference_timesteps=req.inference_timesteps,
                    denoise=req.denoise,
                    normalize=req.normalize,
                )
            finally:
                clear_cuda_cache()
        sample_rate = model.tts_model.sample_rate
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "TTS generation failed model=%s voice=%s prompt_wav_path=%s input_chars=%s",
            req.model,
            req.voice,
            req.prompt_wav_path,
            len(text),
        )
        raise api_error(
            500,
            "TTS_GENERATION_FAILED",
            f"TTS generation failed: {e}",
            retryable=True,
        ) from e

    if req.speed != 1.0:
        pass

    record_voice_usage(db, resolved_voice_id, audio_duration_seconds(wav, sample_rate))
    return audio_response(wav, sample_rate, req.response_format)


@router.post("/v1/audio/voice_clone")
@router.post("/v1/audio/clone")
def clone_voice(req: VoiceCloneRequest, db: Session = Depends(get_db)):
    text = (req.input or "").strip()
    if not text:
        raise api_error(400, "EMPTY_INPUT", "`input` must be a non-empty string.")

    reference_wav_path, voice_id = resolve_voice_reference_path(db, req.voice)
    if not reference_wav_path:
        raise api_error(
            400,
            "VOICE_NOT_FOUND",
            f"`voice` '{req.voice}' not found. Call `/v1/audio/voices` to list available voices.",
        )

    prompt_wav_path = resolve_prompt_wav_path(req.prompt_wav_path)
    prompt_text = (req.prompt_text or "").strip() or None
    # For ultimate-clone use case, default prompt_wav to reference audio.
    if prompt_text and not prompt_wav_path:
        prompt_wav_path = reference_wav_path

    try:
        model = get_model(req.model)
        with generation_lock():
            try:
                wav = model.generate(
                    text=_final_text(text, req.control_instruction),
                    prompt_wav_path=prompt_wav_path,
                    prompt_text=prompt_text,
                    reference_wav_path=reference_wav_path,
                    cfg_value=req.cfg_value,
                    inference_timesteps=req.inference_timesteps,
                    denoise=req.denoise,
                    normalize=req.normalize,
                )
            finally:
                clear_cuda_cache()
        sample_rate = model.tts_model.sample_rate
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(
            "Voice clone failed model=%s voice=%s prompt_wav_path=%s has_prompt_text=%s input_chars=%s",
            req.model,
            req.voice,
            req.prompt_wav_path,
            bool(prompt_text),
            len(text),
        )
        raise api_error(
            500,
            "VOICE_CLONE_FAILED",
            f"Voice clone failed: {e}",
            retryable=True,
        ) from e

    if req.speed != 1.0:
        pass

    record_voice_usage(db, voice_id, audio_duration_seconds(wav, sample_rate))
    return audio_response(wav, sample_rate, req.response_format)
