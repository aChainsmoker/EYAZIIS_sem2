"""Данные и контракт получения текста из других приложений."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class CaptureUnit(StrEnum):
    WORD = "word"
    PARAGRAPH = "paragraph"


@dataclass(frozen=True)
class CapturedText:
    text: str
    source: str


@dataclass(frozen=True)
class CaptureEvent:
    result: CapturedText | None = None
    error: str = ""


class PointerCaptureBackend(Protocol):
    @property
    def running(self) -> bool:
        """Показывает, ожидает ли компонент нажатия горячей клавиши."""
        ...

    def start(self, unit: CaptureUnit) -> None:
        """Включает захват или вызывает CaptureError."""
        ...

    def stop(self) -> None:
        """Освобождает горячую клавишу и завершает фоновые операции."""
        ...

    def poll(self) -> CaptureEvent | None:
        """Возвращает очередной результат, не блокируя интерфейс."""
        ...
