"""Сценарий озвучивания объединяет проверку данных и вызов внедрённого синтезатора."""

import logging
from datetime import UTC, datetime

from literary_voice.application.text import TextProcessor
from literary_voice.domain.errors import (
    EngineUnavailableError,
    ReadingError,
    SynthesisError,
    ValidationError,
)
from literary_voice.domain.models import ReadingResult, SpeechSettings, SynthesisRequest, Voice
from literary_voice.domain.ports import SpeechEngine

logger = logging.getLogger(__name__)


class ReadingService:
    def __init__(
        self,
        engine: SpeechEngine,
        processor: TextProcessor | None = None,
        *,
        voices: tuple[Voice, ...] | None = None,
    ) -> None:
        self.engine = engine
        self.processor = processor if processor is not None else TextProcessor()
        self._voices = voices

    def list_voices(self) -> tuple[Voice, ...]:
        """Возвращает только английские голоса без повторяющихся записей синтезатора."""
        try:
            available = self._voices if self._voices is not None else self.engine.list_voices()
        except ReadingError:
            raise
        except Exception as error:
            logger.exception("Unable to list voices for engine %s", self.engine.id)
            raise EngineUnavailableError(
                "Не удалось получить голоса. Проверьте доступность выбранного режима."
            ) from error
        voices = {
            voice.id: voice
            for voice in available
            if isinstance(voice, Voice)
            and isinstance(voice.id, str)
            and voice.id.strip()
            and isinstance(voice.locale, str)
            and voice.locale.lower().replace("_", "-").split("-")[0] == "en"
        }
        if not voices:
            raise EngineUnavailableError(
                "В этом режиме нет доступных английских голосов. "
                "Выберите другой режим или установите английский голос Windows."
            )
        return tuple(sorted(voices.values(), key=lambda voice: (voice.locale, voice.name)))

    def synthesize(self, text: str, settings: SpeechSettings) -> ReadingResult:
        self._validate_settings(settings)
        prepared_text = self.processor.prepare(text)
        if settings.voice_id not in {voice.id for voice in self.list_voices()}:
            raise ValidationError(
                "Выбранный английский голос больше не доступен. Выберите голос заново."
            )
        request = SynthesisRequest(text=prepared_text, settings=settings)
        try:
            audio = self.engine.synthesize(request)
        except ReadingError:
            raise
        except Exception as error:
            logger.exception("Unable to synthesize speech with engine %s", self.engine.id)
            raise SynthesisError(
                "Не удалось создать запись. Проверьте выбранный режим и повторите попытку."
            ) from error
        if not audio.data:
            raise SynthesisError("Синтезатор вернул пустую запись. Повторите попытку.")
        return ReadingResult(
            audio=audio,
            text=prepared_text,
            settings=settings,
            engine_id=self.engine.id,
            created_at=datetime.now(UTC),
        )

    @staticmethod
    def _validate_settings(settings: SpeechSettings) -> None:
        if not isinstance(settings, SpeechSettings):
            raise ValidationError("Не удалось прочитать настройки озвучивания.")
        if not isinstance(settings.voice_id, str) or not settings.voice_id.strip():
            raise ValidationError("Выберите английский голос диктора.")
        if type(settings.rate) is not int or not -50 <= settings.rate <= 100:
            raise ValidationError("Темп должен быть целым числом от -50 до +100 процентов.")
        if type(settings.volume) is not int or not 0 <= settings.volume <= 100:
            raise ValidationError("Громкость должна быть целым числом от 0 до 100 процентов.")
