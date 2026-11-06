"""Адаптер Windows SAPI с выполнением COM-вызовов в отдельном временном процессе."""

from __future__ import annotations

import io
import json
import logging
import subprocess
import sys
import wave
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from literary_voice.domain.errors import EngineUnavailableError, SynthesisError
from literary_voice.domain.models import AudioResult, SynthesisRequest, Voice

logger = logging.getLogger(__name__)


class WindowsSapiEngine:
    """Использует установленные английские голоса SAPI без передачи текста по сети."""

    id = "sapi"
    name = "Голоса Windows · офлайн"

    def __init__(self, timeout_seconds: float = 180.0) -> None:
        self._timeout_seconds = timeout_seconds

    def list_voices(self) -> tuple[Voice, ...]:
        payload = self._call_worker({"action": "voices"}, timeout=25.0)
        try:
            voices = tuple(Voice(**entry) for entry in payload["voices"])
        except (KeyError, TypeError) as exc:
            raise EngineUnavailableError("Не удалось прочитать список голосов Windows.") from exc
        if not voices:
            raise EngineUnavailableError(
                "Английские голоса SAPI не найдены. Установите английский пакет "
                "синтеза речи в Windows или выберите онлайн-озвучивание."
            )
        return tuple(sorted(voices, key=lambda voice: (voice.locale != "en-GB", voice.name)))

    def synthesize(self, request: SynthesisRequest) -> AudioResult:
        try:
            with TemporaryDirectory(prefix="literary-voice-sapi-") as directory:
                output_path = Path(directory) / "reading.wav"
                self._call_worker(
                    {
                        "action": "synthesize",
                        "text": request.text,
                        "voice_id": request.settings.voice_id,
                        "rate": request.settings.rate,
                        "volume": request.settings.volume,
                        "output_path": str(output_path),
                    },
                    timeout=self._timeout_seconds,
                )
                audio = output_path.read_bytes()
                with wave.open(io.BytesIO(audio), "rb") as stream:
                    if stream.getnframes() == 0:
                        raise ValueError("SAPI returned audio with no samples")
        except EngineUnavailableError:
            raise
        except (OSError, EOFError, ValueError, wave.Error) as exc:
            logger.warning("Invalid audio received from SAPI", exc_info=True)
            raise SynthesisError("Windows не удалось сохранить корректное WAV-аудио.") from exc
        return AudioResult(data=audio, mime_type="audio/wav", extension="wav")

    @staticmethod
    def _call_worker(payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        if sys.platform != "win32":
            raise EngineUnavailableError("Локальные голоса SAPI доступны только в Windows.")
        command = [sys.executable, str(Path(__file__).with_name("sapi_worker.py"))]
        try:
            process = subprocess.run(
                command,
                input=json.dumps(payload, ensure_ascii=False),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except subprocess.TimeoutExpired as exc:
            raise SynthesisError(
                "Windows не завершила озвучивание за отведённое время. "
                "Попробуйте более короткий отрывок или другой голос."
            ) from exc
        except OSError as exc:
            raise EngineUnavailableError("Не удалось запустить синтезатор Windows.") from exc
        try:
            response = json.loads(process.stdout)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("SAPI worker returned an invalid response: %s", process.stderr)
            raise EngineUnavailableError("Синтезатор Windows вернул некорректный ответ.") from exc
        if not isinstance(response, dict):
            raise EngineUnavailableError("Синтезатор Windows вернул некорректный ответ.")
        if process.returncode != 0 or not response.get("ok"):
            error = response.get("error", "synthesis_failed")
            if error == "missing_dependency":
                raise EngineUnavailableError(
                    "Для локальных голосов Windows установите зависимости приложения "
                    "(пакет pywin32)."
                )
            if error == "voice_not_found":
                raise EngineUnavailableError(
                    "Выбранный английский голос больше недоступен. Обновите список голосов."
                )
            logger.warning("SAPI worker failed: %s", response.get("detail", error))
            raise SynthesisError("Синтезатор Windows не смог создать аудио. Выберите другой голос.")
        return response
