from threading import Lock

from src.errors import TranslationError, TranslationModelError

SUPPORTED_DIRECTIONS = (("en", "ru"), ("ru", "en"))
_lock = Lock()
_translations = {}
_INSTALL_INSTRUCTION = "Подготовьте переводчик командой: python -m src.translation.prepare"


def translate(text: str, source: str = "en", target: str = "ru") -> str:
    if source not in {"ru", "en"} or target not in {"ru", "en"}:
        raise TranslationError("Поддерживаются исходный и целевой языки ru/en.")
    if not text.strip():
        raise TranslationError("Документ не содержит текста для перевода.")
    if source == target:
        return text
    direction = (source, target)
    with _lock:
        if direction not in _translations:
            try:
                import argostranslate.package
                import argostranslate.translate
                if not any(package.from_code == source and package.to_code == target
                           for package in argostranslate.package.get_installed_packages()):
                    raise LookupError("Missing translation package")
                languages = {language.code: language for language in argostranslate.translate.get_installed_languages()}
                model = languages[source].get_translation(languages[target])
                if model is None:
                    raise LookupError("Missing translation model")
                _translations[direction] = model
            except Exception as exc:
                raise TranslationModelError(
                    f"Модель Argos {source.upper()}→{target.upper()} недоступна. " + _INSTALL_INSTRUCTION
                ) from exc
        try:
            result = _translations[direction].translate(text).strip()
        except Exception as exc:
            raise TranslationError("Argos не удалось перевести документ.") from exc
    if not result:
        raise TranslationError("Argos вернул пустой перевод.")
    return result
