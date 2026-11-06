"""Подготовка текста с сохранением литературной пунктуации и строк стихотворений."""

import codecs
import re
import unicodedata

from literary_voice.domain.errors import ValidationError


def _has_control_characters(text: str) -> bool:
    return any(
        unicodedata.category(character) in {"Cc", "Cs"} and character not in "\n\r\t"
        for character in text
    )


def decode_text_file(data: bytes, max_bytes: int = 1_000_000) -> str:
    """Декодирует TXT-файлы в UTF-8 или UTF-16 с меткой BOM.

    Кодировка не определяется предположительно: ошибка может незаметно исказить
    английскую пунктуацию и имена. Редактор также поддерживает обычную вставку.
    """
    if not isinstance(data, bytes):
        raise ValidationError("Не удалось прочитать текстовый файл.")
    if not data:
        raise ValidationError("Текстовый файл пуст.")
    if len(data) > max_bytes:
        raise ValidationError(f"Файл слишком большой. Максимальный размер: {max_bytes:,} байт.")
    encoding = (
        "utf-16" if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)) else "utf-8-sig"
    )
    try:
        text = data.decode(encoding)
    except UnicodeError as error:
        raise ValidationError(
            "Не удалось прочитать кодировку файла. Сохраните TXT в UTF-8 "
            "или UTF-16 с BOM, либо вставьте текст в редактор."
        ) from error
    if _has_control_characters(text):
        raise ValidationError("Файл содержит служебные символы. Загрузите обычный TXT.")
    return text


class TextProcessor:
    """Нормализует прозу и отклоняет текст, непригодный для английского диктора.

    Проверка алфавита помогает обнаружить случайно вставленный текст с другой
    письменностью. Это не статистическое определение языка: короткие цитаты
    на английском нельзя надёжно отличить от других языков с латиницей.
    """

    def __init__(self, max_characters: int = 20_000) -> None:
        if type(max_characters) is not int or max_characters <= 0:
            raise ValueError("max_characters must be a positive integer")
        self.max_characters = max_characters

    def prepare(self, text: str) -> str:
        if not isinstance(text, str):
            raise ValidationError("Введите английский текст для озвучивания.")
        if _has_control_characters(text):
            raise ValidationError("Текст содержит недопустимые служебные символы.")

        prepared = unicodedata.normalize("NFC", text)
        prepared = prepared.replace("\r\n", "\n").replace("\r", "\n")
        prepared = prepared.replace("\u2028", "\n").replace("\u2029", "\n\n")
        # При копировании из PDF и текстовых редакторов часто появляются невидимые символы.
        prepared = prepared.translate({ord(c): None for c in "\ufeff\u200b\u00ad"})
        prepared = "\n".join(
            re.sub(r"[^\S\n]+", " ", line).strip() for line in prepared.split("\n")
        )
        prepared = re.sub(r"\n{3,}", "\n\n", prepared).strip()

        if not prepared:
            raise ValidationError("Введите или загрузите текст для озвучивания.")
        if len(prepared) > self.max_characters:
            raise ValidationError(
                f"Текст слишком длинный: {len(prepared):,} символов. "
                f"Допускается не более {self.max_characters:,}; разделите произведение на отрывки."
            )

        letters = [character for character in prepared if character.isalpha()]
        latin_count = sum("LATIN" in unicodedata.name(character, "") for character in letters)
        if not letters:
            raise ValidationError("Текст должен содержать английские слова.")
        if latin_count / len(letters) < 0.7:
            raise ValidationError(
                "Выбран английский язык озвучивания. Введите текст "
                "преимущественно на английском языке."
            )
        return prepared
