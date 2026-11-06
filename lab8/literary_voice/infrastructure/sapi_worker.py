"""Внутренний обработчик JSON-запросов из stdin, работающий с COM-объектами Windows.

Родительский процесс запускает этот Python-файл напрямую, поэтому относительные
импорты из пакета не допускаются. Результат операции и диагностика возвращаются
одним JSON-объектом в кодировке UTF-8.
"""

from __future__ import annotations

import json
import locale
import math
import sys
from typing import Any

SPEAK_AS_PLAIN_TEXT = 16  # Флаг обычного текста: SpeechVoiceSpeakFlags.SVSFIsNotXML.
CREATE_FOR_WRITE = 3  # Режим создания файла для записи: SpeechStreamFileMode.SSFMCreateForWrite.


def english_locale(language_attribute: str) -> str | None:
    """Атрибут языка SAPI содержит шестнадцатеричные идентификаторы LCID через точку с запятой."""
    for value in language_attribute.split(";"):
        try:
            language_id = int(value.strip(), 16)
        except ValueError:
            continue
        # Младшие десять бит содержат основной идентификатор языка Windows.
        if language_id & 0x3FF == 0x09:
            return locale.windows_locale.get(language_id, "en-001").replace("_", "-")
    return None


def sapi_rate(rate_percent: int) -> int:
    """Переводит относительный темп в целочисленную шкалу конкретного синтезатора SAPI.

    Ноль сохраняется; половинная и двойная скорости соответствуют границам шкалы.
    Воспринимаемая скорость приблизительна: каждый голос SAPI трактует темп по-своему.
    """
    return max(-10, min(10, round(10 * math.log2(1 + rate_percent / 100))))


def _attribute(token: Any, name: str, default: str = "") -> str:
    try:
        return str(token.GetAttribute(name))
    except Exception:
        return default


def execute(payload: dict[str, Any], dispatch: Any) -> dict[str, Any]:
    """Выполняет одну операцию; внедрение зависимости позволяет тестировать COM-вызовы."""
    speaker = dispatch("SAPI.SpVoice")
    collection = speaker.GetVoices()
    tokens: list[tuple[Any, str]] = []
    for index in range(collection.Count):
        token = collection.Item(index)
        token_locale = english_locale(_attribute(token, "Language"))
        if token_locale:
            tokens.append((token, token_locale))

    if payload.get("action") == "voices":
        return {
            "ok": True,
            "voices": [
                {
                    "id": token.Id,
                    "name": token.GetDescription(),
                    "locale": token_locale,
                    "gender": _attribute(token, "Gender"),
                }
                for token, token_locale in tokens
            ],
        }
    if payload.get("action") != "synthesize":
        return {"ok": False, "error": "unknown_action"}

    token = next((token for token, _ in tokens if token.Id == payload.get("voice_id")), None)
    if token is None:
        return {"ok": False, "error": "voice_not_found"}
    speaker.Voice = token
    speaker.Rate = sapi_rate(payload["rate"])
    speaker.Volume = payload["volume"]
    stream = dispatch("SAPI.SpFileStream")
    stream.Open(payload["output_path"], CREATE_FOR_WRITE, False)
    try:
        speaker.AudioOutputStream = stream
        # Литературный текст всегда читается как обычный, включая угловые скобки.
        speaker.Speak(payload["text"], SPEAK_AS_PLAIN_TEXT)
    finally:
        stream.Close()
    return {"ok": True}


def main() -> None:
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        print(json.dumps({"ok": False, "error": "missing_dependency"}))
        return

    initialized = False
    try:
        payload = json.load(sys.stdin)
        pythoncom.CoInitialize()
        initialized = True
        response = execute(payload, win32com.client.Dispatch)
    except Exception as exc:
        response = {"ok": False, "error": "synthesis_failed", "detail": str(exc)}
    finally:
        if initialized:
            pythoncom.CoUninitialize()
    print(json.dumps(response, ensure_ascii=False))


if __name__ == "__main__":
    main()
