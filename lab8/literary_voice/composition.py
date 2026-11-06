"""Корень композиции: создание прикладных сервисов и выбор конкретных адаптеров."""

import sys
from pathlib import Path

from literary_voice.application.capture import PointerCaptureService
from literary_voice.application.library import LibraryService
from literary_voice.domain.errors import ValidationError
from literary_voice.domain.ports import SpeechEngine
from literary_voice.infrastructure.edge import EdgeTtsEngine
from literary_voice.infrastructure.library import FileSystemLibraryRepository
from literary_voice.infrastructure.pointer import WindowsPointerCapture
from literary_voice.infrastructure.sapi import WindowsSapiEngine

ENGINE_LABELS = {
    "sapi": "Windows · локальные голоса",
    "edge": "Edge TTS · нейросетевые голоса",
}
LITERATURE_ROOT = Path(__file__).resolve().parents[1] / "Литература"


def create_pointer_capture_service() -> PointerCaptureService:
    return PointerCaptureService(WindowsPointerCapture())


def create_library_service() -> LibraryService:
    return LibraryService(FileSystemLibraryRepository(LITERATURE_ROOT))


def default_engine_id() -> str:
    return "sapi" if sys.platform == "win32" else "edge"


def create_engine(engine_id: str) -> SpeechEngine:
    if engine_id == "sapi":
        return WindowsSapiEngine()
    if engine_id == "edge":
        return EdgeTtsEngine()
    raise ValidationError("Неизвестный режим синтеза речи.")
