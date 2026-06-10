import io

import numpy as np
import soundfile as sf
from fastapi.responses import Response
from pydub import AudioSegment

from api.config import PCM_CHANNELS, PCM_ENCODING, PCM_SAMPLE_WIDTH_BITS


def to_int16_pcm_bytes(wav: np.ndarray) -> bytes:
    wav = np.asarray(wav, dtype=np.float32)
    wav = np.clip(wav, -1.0, 1.0)
    return (wav * 32767.0).astype(np.int16).tobytes()


def to_opus_bytes(wav: np.ndarray, sample_rate: int) -> bytes:
    audio = AudioSegment(
        data=to_int16_pcm_bytes(wav),
        sample_width=2,
        frame_rate=sample_rate,
        channels=1,
    )
    opus_io = io.BytesIO()
    audio.export(opus_io, format="opus", codec="libopus")
    return opus_io.getvalue()


def audio_response(wav: np.ndarray, sample_rate: int, response_format: str) -> Response:
    if response_format == "pcm":
        return Response(
            content=to_int16_pcm_bytes(wav),
            media_type="application/octet-stream",
            headers={
                "X-Sample-Rate": str(sample_rate),
                "X-Channels": PCM_CHANNELS,
                "X-Sample-Width-Bits": PCM_SAMPLE_WIDTH_BITS,
                "X-PCM-Encoding": PCM_ENCODING,
            },
        )

    if response_format == "opus":
        return Response(content=to_opus_bytes(wav, sample_rate), media_type="audio/opus")

    wav_io = io.BytesIO()
    sf.write(wav_io, wav, sample_rate, format="WAV")
    return Response(content=wav_io.getvalue(), media_type="audio/wav")


def audio_duration_seconds(wav: np.ndarray, sample_rate: int) -> float:
    if sample_rate <= 0:
        return 0.0
    return float(len(wav) / sample_rate)
