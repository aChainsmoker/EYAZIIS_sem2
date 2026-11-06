"""Сценарий получения и проверки текста под указателем мыши."""

from literary_voice.application.text import TextProcessor
from literary_voice.domain.capture import (
    CapturedText,
    CaptureEvent,
    CaptureUnit,
    PointerCaptureBackend,
)
from literary_voice.domain.errors import CaptureError, ReadingError


class PointerCaptureService:
    def __init__(
        self, backend: PointerCaptureBackend, processor: TextProcessor | None = None
    ) -> None:
        self._backend = backend
        self._processor = processor if processor is not None else TextProcessor()

    @property
    def running(self) -> bool:
        return self._backend.running

    def start(self, unit: CaptureUnit) -> None:
        if not isinstance(unit, CaptureUnit):
            raise CaptureError("Выберите захват слова или абзаца.")
        self._backend.start(unit)

    def stop(self) -> None:
        self._backend.stop()

    def poll(self) -> CaptureEvent | None:
        event = self._backend.poll()
        if event is None or event.result is None:
            return event
        try:
            text = self._processor.prepare(event.result.text)
        except ReadingError as error:
            return CaptureEvent(error=f"Полученный текст не добавлен в редактор: {error}")
        return CaptureEvent(result=CapturedText(text, event.result.source))
