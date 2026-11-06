"""Контракт синтезатора, реализуемый адаптерами локального и сетевого синтеза."""

from typing import Protocol

from literary_voice.domain.models import AudioResult, SynthesisRequest, Voice


class SpeechEngine(Protocol):
    id: str
    name: str

    def list_voices(self) -> tuple[Voice, ...]:
        """Возвращает голоса, поддерживаемые этим синтезатором."""
        ...

    def synthesize(self, request: SynthesisRequest) -> AudioResult:
        """Создаёт полную аудиозапись или вызывает исключение ReadingError."""
        ...
