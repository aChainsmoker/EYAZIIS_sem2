"""Сетевой нейросетевой синтез речи через Python-клиент edge-tts."""

from __future__ import annotations

import asyncio
import importlib
import logging
from collections.abc import Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, TypeVar

from literary_voice.domain.errors import EngineUnavailableError, SynthesisError
from literary_voice.domain.models import AudioResult, SynthesisRequest, Voice

logger = logging.getLogger(__name__)
T = TypeVar("T")


class EdgeTtsEngine:
    """Предоставляет асинхронный сетевой клиент через синхронный контракт синтезатора.

    Каждая операция создаёт собственный цикл событий в рабочем потоке. Циклы
    и сетевые сессии не разделяются между перезапусками скрипта Streamlit
    или пользовательскими сессиями.
    """

    id = "edge"
    name = "Нейросетевые голоса · онлайн"

    def __init__(self, timeout_seconds: float = 180.0) -> None:
        self._timeout_seconds = timeout_seconds

    def list_voices(self) -> tuple[Voice, ...]:
        client = self._load_client()
        try:
            entries = self._run_async(client.list_voices, timeout=25.0)
            voices = tuple(
                Voice(
                    id=entry["ShortName"],
                    name=entry.get("FriendlyName", entry["ShortName"]),
                    locale=entry["Locale"],
                    gender=entry.get("Gender", ""),
                )
                for entry in entries
                if entry.get("Locale", "").lower().startswith("en-")
            )
        except Exception as exc:
            logger.warning("Could not retrieve Edge voices", exc_info=True)
            raise EngineUnavailableError(
                "Не удалось загрузить онлайн-голоса. Проверьте интернет или "
                "выберите локальные голоса Windows."
            ) from exc
        if not voices:
            raise EngineUnavailableError("Сервис не вернул английские голоса.")
        priority = {"en-GB": 0, "en-US": 1}
        return tuple(
            sorted(
                voices,
                key=lambda voice: (priority.get(voice.locale, 2), voice.locale, voice.name),
            )
        )

    def synthesize(self, request: SynthesisRequest) -> AudioResult:
        client = self._load_client()
        try:
            with TemporaryDirectory(prefix="literary-voice-edge-") as directory:
                output_path = Path(directory) / "reading.mp3"

                async def save_audio() -> None:
                    communicator = client.Communicate(
                        request.text,
                        voice=request.settings.voice_id,
                        rate=f"{request.settings.rate:+d}%",
                        # Громкость edge-tts задаётся изменением относительно 100 %,
                        # а не абсолютным уровнем.
                        volume=f"{request.settings.volume - 100:+d}%",
                        connect_timeout=10,
                        receive_timeout=40,
                    )
                    await communicator.save(str(output_path))

                self._run_async(save_audio, timeout=self._timeout_seconds)
                audio = output_path.read_bytes()
                if not audio:
                    raise ValueError("The service returned an empty audio file")
        except Exception as exc:
            logger.warning("Edge speech synthesis failed", exc_info=True)
            raise SynthesisError(
                "Онлайн-сервис не смог создать аудио. Проверьте интернет, "
                "повторите попытку или выберите локальные голоса Windows."
            ) from exc
        return AudioResult(data=audio, mime_type="audio/mpeg", extension="mp3")

    @staticmethod
    def _load_client() -> Any:
        try:
            return importlib.import_module("edge_tts")
        except ImportError as exc:
            raise EngineUnavailableError(
                "Для онлайн-озвучивания установите зависимости приложения (пакет edge-tts)."
            ) from exc

    @staticmethod
    def _run_async(factory: Callable[[], Coroutine[Any, Any, T]], timeout: float) -> T:
        async def bounded_operation() -> T:
            return await asyncio.wait_for(factory(), timeout=timeout)

        def run() -> T:
            return asyncio.run(bounded_operation())

        with ThreadPoolExecutor(max_workers=1, thread_name_prefix="edge-tts") as executor:
            return executor.submit(run).result()
