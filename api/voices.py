from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from api.config import VOICE_AUDIO_EXTENSIONS, get_voices_dir
from api.errors import api_error
from api.models import Voice, VoiceStat
from api.schemas import VoiceLabelOut, VoiceOut, VoiceStatOut


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _display_name(audio_path: Path) -> str:
    return audio_path.stem.replace("_", " ")


def _normalize_text(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _normalize_lang(value: Optional[str]) -> Optional[str]:
    normalized = _normalize_text(value)
    if not normalized:
        return None
    if normalized in {"zh", "zh-cn", "cn", "chinese", "中文", "汉语", "普通话"}:
        return "zh"
    if normalized in {"en", "en-us", "en-gb", "english", "英文"}:
        return "en"
    return normalized


def _match_contains(source: Optional[str], keyword: str) -> bool:
    return keyword in _normalize_text(source)


def _voice_lang_matches(voice: Voice, normalized_lang: str) -> bool:
    if _normalize_lang(voice.language) == normalized_lang:
        return True

    for label in voice.labels:
        if _normalize_text(label.key) in {"language", "lang", "locale", "source"}:
            if _normalize_lang(label.value) == normalized_lang:
                return True
    return False


def _voice_gender_matches(voice: Voice, gender_keyword: str) -> bool:
    if _match_contains(voice.gender, gender_keyword):
        return True
    for label in voice.labels:
        if _normalize_text(label.key) in {"gender", "sex"} and _match_contains(label.value, gender_keyword):
            return True
    return False


def _voice_accent_matches(voice: Voice, accent_keyword: str) -> bool:
    if _match_contains(voice.category, accent_keyword):
        return True
    if _match_contains(voice.description, accent_keyword):
        return True
    for label in voice.labels:
        if _normalize_text(label.key) in {"accent", "tone", "style", "role_hint", "voice_display_name"}:
            if _match_contains(label.value, accent_keyword):
                return True
    return False


def _safe_voice_id(relative_path: str, existing_ids: set[str]) -> str:
    stem = Path(relative_path).stem
    if stem not in existing_ids:
        return stem

    candidate = re.sub(r"[^a-zA-Z0-9_-]+", "_", Path(relative_path).with_suffix("").as_posix()).strip("_")
    if not candidate:
        candidate = stem

    base = candidate
    index = 2
    while candidate in existing_ids:
        candidate = f"{base}_{index}"
        index += 1
    return candidate


def sync_voice_directory(db: Session) -> None:
    voices_dir = get_voices_dir()
    if not voices_dir.exists():
        return

    existing_voices = list(db.scalars(select(Voice)).all())
    existing_by_file: dict[str, Voice] = {}
    for voice in existing_voices:
        # If multiple voice_id share the same file_name, keep the first one.
        # This keeps startup sync stable and avoids generating conflicting IDs.
        existing_by_file.setdefault(voice.file_name, voice)
    existing_ids = {voice.voice_id for voice in existing_voices}
    now = utc_now()
    changed = False

    # Only sync top-level WAV files under VOICE_REFERENCES_DIR (e.g. assets/voices/*.wav).
    # Subdirectories (e.g. legacy mp3 sources) are ignored.
    for audio_path in sorted(voices_dir.iterdir()):
        if not audio_path.is_file() or audio_path.suffix.lower() != ".wav":
            continue

        file_name = audio_path.name
        voice = existing_by_file.get(file_name)
        if voice is not None:
            if not voice.name:
                voice.name = _display_name(audio_path)
            voice.updated_at = now
            changed = True
            continue

        voice_id = _safe_voice_id(file_name, existing_ids)
        existing_ids.add(voice_id)
        db.add(
            Voice(
                voice_id=voice_id,
                name=_display_name(audio_path),
                description="",
                file_name=file_name,
                enabled=True,
                created_at=now,
                updated_at=now,
                stats=VoiceStat(request_count=0, total_audio_seconds=0.0),
            )
        )
        changed = True

    if changed:
        db.commit()


def voice_to_output(voice: Voice) -> VoiceOut:
    voices_dir = get_voices_dir()
    reference_path = (voices_dir / voice.file_name).resolve()
    return VoiceOut(
        id=voice.voice_id,
        database_id=voice.id,
        voice_id=voice.voice_id,
        name=voice.name,
        description=voice.description,
        category=voice.category,
        language=voice.language,
        gender=voice.gender,
        file_name=voice.file_name,
        reference_wav_path=str(reference_path),
        relative_path=voice.file_name,
        enabled=voice.enabled,
        owner=voice.owner,
        version=voice.version,
        created_at=voice.created_at,
        updated_at=voice.updated_at,
        labels=[VoiceLabelOut(key=label.key, value=label.value) for label in voice.labels],
        stats=(
            VoiceStatOut(
                request_count=voice.stats.request_count,
                total_audio_seconds=voice.stats.total_audio_seconds,
                last_used_at=voice.stats.last_used_at,
            )
            if voice.stats
            else None
        ),
    )


def list_enabled_voices(
    db: Session,
    *,
    accent: Optional[str] = None,
    gender: Optional[str] = None,
    lang: Optional[str] = None,
) -> list[Voice]:
    stmt = (
        select(Voice)
        .where(Voice.enabled.is_(True))
        .options(selectinload(Voice.labels), selectinload(Voice.stats))
        .order_by(Voice.voice_id)
    )
    voices = list(db.scalars(stmt).all())

    accent_keyword = _normalize_text(accent)
    gender_keyword = _normalize_text(gender)
    normalized_lang = _normalize_lang(lang)

    if accent_keyword:
        voices = [voice for voice in voices if _voice_accent_matches(voice, accent_keyword)]
    if gender_keyword:
        voices = [voice for voice in voices if _voice_gender_matches(voice, gender_keyword)]
    if normalized_lang:
        voices = [voice for voice in voices if _voice_lang_matches(voice, normalized_lang)]
    return voices


def resolve_voice(db: Session, voice: str) -> Optional[Voice]:
    normalized_voice = (voice or "").strip().lower()
    if not normalized_voice:
        return None

    for item in list_enabled_voices(db):
        candidates = {
            item.voice_id.lower(),
            item.name.strip().lower(),
            item.file_name.lower(),
        }
        if normalized_voice in candidates:
            return item
    return None


def resolve_voice_reference_path(db: Session, voice: str) -> tuple[Optional[str], Optional[str]]:
    item = resolve_voice(db, voice)
    if item is None:
        return None, None
    return str((get_voices_dir() / item.file_name).resolve()), item.voice_id


def resolve_voice_by_id(db: Session, voice_id: str) -> Optional[Voice]:
    normalized = (voice_id or "").strip()
    if not normalized:
        return None
    stmt = (
        select(Voice)
        .where(Voice.enabled.is_(True), Voice.voice_id == normalized)
        .options(selectinload(Voice.labels), selectinload(Voice.stats))
        .limit(1)
    )
    return db.scalars(stmt).first()


def get_voice_audio_file_path(voice: Voice) -> Path:
    voices_dir = get_voices_dir()
    resolved_path = (voices_dir / voice.file_name).resolve()
    if not is_relative_to(resolved_path, voices_dir):
        raise api_error(
            400,
            "VOICE_AUDIO_PATH_NOT_ALLOWED",
            "Resolved voice audio path is outside VOICE_REFERENCES_DIR.",
        )
    return resolved_path


def resolve_prompt_wav_path(prompt_wav_path: Optional[str]) -> Optional[str]:
    raw_path = (prompt_wav_path or "").strip()
    if not raw_path:
        return None

    voices_dir = get_voices_dir()
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = voices_dir / path
    resolved_path = path.resolve()

    if not is_relative_to(resolved_path, voices_dir):
        raise api_error(
            400,
            "PROMPT_AUDIO_PATH_NOT_ALLOWED",
            "`prompt_wav_path` must point to an audio file under VOICE_REFERENCES_DIR.",
        )
    if not resolved_path.is_file():
        raise api_error(
            400,
            "PROMPT_AUDIO_NOT_FOUND",
            f"`prompt_wav_path` '{raw_path}' does not exist or is not a file.",
        )
    if resolved_path.suffix.lower() not in VOICE_AUDIO_EXTENSIONS:
        raise api_error(
            400,
            "PROMPT_AUDIO_FORMAT_UNSUPPORTED",
            f"`prompt_wav_path` must use one of: {', '.join(sorted(VOICE_AUDIO_EXTENSIONS))}.",
        )
    return str(resolved_path)


def record_voice_usage(db: Session, voice_id: Optional[str], audio_seconds: float) -> None:
    if not voice_id:
        return

    stat = db.get(VoiceStat, voice_id)
    if stat is None:
        stat = VoiceStat(voice_id=voice_id, request_count=0, total_audio_seconds=0.0)
        db.add(stat)

    stat.request_count += 1
    stat.total_audio_seconds += audio_seconds
    stat.last_used_at = utc_now()
    db.commit()
