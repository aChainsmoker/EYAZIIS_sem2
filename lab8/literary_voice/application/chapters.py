"""Подготовка целых глав в виде удобных для управления фрагментов для чтения без потери текста."""

import re

from literary_voice.application.text import TextProcessor

MAX_READING_CHARACTERS = 20_000


def split_chapter(text: str, max_characters: int = MAX_READING_CHARACTERS) -> tuple[str, ...]:
    """Сохраняет каждый символ, предпочитая границы абзаца, строки, предложения и слова.
    Файлы на диске остаются целыми. Делится только запрос на озвучивание, чтобы длинная
    глава не создавала чрезмерно большой WAV-файл в памяти сессии.
    Конкатенация возвращённых фрагментов восстанавливает подготовленную главу.
    """
    if type(max_characters) is not int or max_characters <= 0:
        raise ValueError("max_characters must be a positive integer")
    prepared = TextProcessor(max_characters=max(len(text), max_characters)).prepare(text)
    fragments: list[str] = []
    start = 0
    while len(prepared) - start > max_characters:
        limit = start + max_characters
        minimum = start + max_characters // 2
        boundary = 0
        for separator in ("\n\n", "\n"):
            position = prepared.rfind(separator, minimum, limit)
            if position >= 0:
                boundary = position + len(separator)
                break
        if not boundary:
            sentences = list(re.finditer(r"[.!?][’\"')]*\s+", prepared[minimum:limit]))
            if sentences:
                boundary = minimum + sentences[-1].end()
        if not boundary:
            position = prepared.rfind(" ", minimum, limit)
            boundary = position + 1 if position >= 0 else limit
        fragments.append(prepared[start:boundary])
        start = boundary
    fragments.append(prepared[start:])
    return tuple(fragments)
