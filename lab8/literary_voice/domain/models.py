"""Неизменяемые данные для обмена между приложением и синтезаторами речи."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Voice:
    id: str
    name: str
    locale: str
    gender: str = ""


@dataclass(frozen=True)
class SpeechSettings:
    """Темп задаётся в процентах относительно обычной скорости чтения синтезатора."""

    voice_id: str
    rate: int = 0
    volume: int = 100


@dataclass(frozen=True)
class SynthesisRequest:
    text: str
    settings: SpeechSettings


@dataclass(frozen=True)
class AudioResult:
    data: bytes
    mime_type: str
    extension: str


@dataclass(frozen=True)
class ReadingResult:
    audio: AudioResult
    text: str
    settings: SpeechSettings
    engine_id: str
    created_at: datetime
