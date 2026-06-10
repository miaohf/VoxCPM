import os
from pathlib import Path


DEFAULT_MODEL = "openbmb/VoxCPM2"
VOICE_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".ogg"}
PCM_CHANNELS = "1"
PCM_SAMPLE_WIDTH_BITS = "16"
PCM_ENCODING = "signed-integer-little-endian"


def get_allowed_models() -> list[str]:
    raw = os.getenv("ALLOWED_MODELS", DEFAULT_MODEL)
    models = [item.strip() for item in raw.split(",") if item.strip()]
    return models or [DEFAULT_MODEL]


def get_voices_dir() -> Path:
    voices_dir = os.getenv("VOICE_REFERENCES_DIR", "assets/voices")
    return Path(voices_dir).expanduser().resolve()


def get_database_url() -> str:
    explicit_url = os.getenv("DATABASE_URL")
    if explicit_url:
        return explicit_url

    db_path = Path(os.getenv("VOICES_DB_PATH", "data/voices.sqlite")).expanduser()
    if not db_path.is_absolute():
        db_path = Path.cwd() / db_path
    return f"sqlite:///{db_path.resolve()}"


def get_host() -> str:
    return os.getenv("HOST", "0.0.0.0")


def get_port() -> int:
    return int(os.getenv("PORT", "8808"))
