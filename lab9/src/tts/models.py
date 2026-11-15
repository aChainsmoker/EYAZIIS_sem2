from dataclasses import dataclass


@dataclass(frozen=True)
class Voice:
    id: str
    name: str
    locale: str
    gender: str = ""


@dataclass(frozen=True)
class SpeechSettings:
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
