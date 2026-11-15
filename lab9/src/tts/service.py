import io
import re
import unicodedata
import wave

from src.config import CONFIG
from src.errors import SynthesisError, VoiceUnavailableError
from src.tts.models import SpeechSettings, SynthesisRequest
from src.tts.sapi import WindowsSapiEngine


def _chunks(text: str, limit: int):
    """Предложения сохраняются целиком, кроме превышающих лимит: они делятся по словам."""
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.translate({ord(character): None for character in "\ufeff\u200b\u00ad"})
    if any(unicodedata.category(character) in {"Cc", "Cs"} and character not in "\n\t" for character in text):
        raise SynthesisError("Документ содержит недопустимые для озвучки служебные символы.")
    current = ""
    for sentence in re.split(r"(?<=[.!?])\s+|\n\s*\n", text.strip()):
        if not sentence.strip():
            continue
        units = [sentence] if len(sentence) <= limit else re.findall(r"\S+", sentence)
        for unit in units:
            # Даже одно очень длинное слово не теряется и не обрезается.
            for offset in range(0, len(unit), limit):
                part = unit[offset:offset + limit]
                if current and len(current) + len(part) + 1 > limit:
                    yield current
                    current = ""
                current = current + " " + part if current else part
    if current:
        yield current


def synthesize_document(text: str, title: str, language: str = "en") -> dict:
    settings = CONFIG.get("tts", {})
    chunk_size = int(settings.get("chunk_characters", 2000))
    timeout = float(settings.get("timeout_seconds", 180))
    if not 1 <= chunk_size <= 20000 or timeout <= 0:
        raise ValueError("Проверьте размер фрагмента и тайм-аут SAPI в TOML.")
    engine = WindowsSapiEngine(timeout_seconds=timeout)
    voices = engine.list_voices(language)
    voice_id = settings.get("voices", {}).get(language, "")
    if not voice_id and language == "en":
        voice_id = settings.get("voice_id", "")
    voice_id = voice_id or voices[0].id
    if voice_id not in {voice.id for voice in voices}:
        raise VoiceUnavailableError(f"Указанный в TOML голос для языка {language.upper()} недоступен.")
    speech_settings = SpeechSettings(voice_id=voice_id)
    output = io.BytesIO()
    format_info = None
    with wave.open(output, "wb") as destination:
        destination.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        for chunk in _chunks(text, chunk_size):
            result = engine.synthesize(SynthesisRequest(chunk, speech_settings))
            with wave.open(io.BytesIO(result.data), "rb") as source:
                current_format = (source.getnchannels(), source.getsampwidth(), source.getframerate(),
                                  source.getcomptype(), source.getcompname())
                if format_info is None:
                    format_info = current_format
                    destination.setparams((*current_format[:3], 0, *current_format[3:]))
                elif current_format != format_info:
                    raise SynthesisError("SAPI вернул WAV-фрагменты с несовместимыми форматами.")
                destination.writeframes(source.readframes(source.getnframes()))
        if format_info is None:
            raise SynthesisError("В документе нет текста для озвучки.")
    return dict(
        audio=output.getvalue(), mime_type="audio/wav", filename=f"{title}.wav",
        parameters={"voice_id": voice_id, "rate": speech_settings.rate,
                    "volume": speech_settings.volume, "chunk_characters": chunk_size},
    )
