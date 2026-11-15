import re

from src.bot.models import Command
from src.errors import CommandError

_VERBS = {
    "search": r"(?:найди|найти|поищи|поиск|find|search|look\s+for)",
    "summary": r"(?:сделай(?:\s+мне)?\s+(?:реферирование|реферат)|реферирование|составь\s+реферат|сократи|summari[sz]e|(?:make|create)\s+(?:a\s+)?summary(?:\s+of)?)",
    "translation": r"(?:переведи|перевести|translate)",
    "speech": r"(?:озвучь|озвучить|прочитай(?:\s+вслух)?|read(?:\s+(?:aloud|out))?|speak|voice)",
}
_OBJECT = r"(?:документ(?:а)?|текст(?:а)?|файл(?:а)?|(?:(?:the|this|selected)\s+)?(?:document|text|file))"
_SEARCH_FILLER = r"(?:в\s+(?:тексте|текстах|документе|документах)|in\s+(?:the\s+)?(?:texts?|documents?)|for)"
_QUOTES = {'"': '"', "'": "'", "«": "»", "“": "”", "„": "“"}
_NEXT_ACTION = re.compile(
    r"(?:\b(?:и|затем|потом|and|then)\b|[;,\n.!?])\s*(?:пожалуйста\s+|please\s+)?(?:"
    + "|".join(_VERBS.values()) + r")\b", re.I,
)
_TARGETS = {"русский": "ru", "russian": "ru", "ru": "ru",
            "английский": "en", "english": "en", "en": "en"}


def _search_argument(value: str) -> str:
    value = value.strip()
    outside = []
    closing = None
    for character in value:
        if closing is not None:
            if character == closing:
                closing = None
            outside.append(" ")
        elif character in _QUOTES and (not outside or outside[-1].isspace()):
            closing = _QUOTES[character]
            outside.append(" ")
        else:
            outside.append(character)
    if closing is not None:
        raise CommandError("Закройте кавычки вокруг поискового запроса.")
    if _NEXT_ACTION.search("".join(outside)):
        raise CommandError("Укажите одно действие в одном сообщении.")
    if value and value[0] in _QUOTES:
        end = value.find(_QUOTES[value[0]], 1)
        if end < 0 or value[end + 1:].strip(" .!?\t\r\n"):
            raise CommandError("После поискового запроса в кавычках обнаружен лишний текст.")
        value = value[1:end].strip()
    if not value or not value.strip(".!?"):
        raise CommandError("Укажите, что нужно найти в выбранном тексте.")
    return value


def parse_command(text: str) -> Command:
    if not isinstance(text, str) or not text.strip():
        raise CommandError("Введите или произнесите команду.")
    text = re.sub(r"^(?:пожалуйста|please)[,\s]+", "", text.strip(), flags=re.I)
    for action, verb in _VERBS.items():
        match = re.match(r"^" + verb + r"\b", text, flags=re.I)
        if not match:
            continue
        tail = text[match.end():].strip()
        tail = re.sub(r"^мне(?:\s+|$)", "", tail, flags=re.I)
        if action == "search":
            tail = re.sub(r"^" + _SEARCH_FILLER + r"(?:\s*:\s*|\s+|$)", "", tail, count=1, flags=re.I)
            return Command(action, _search_argument(tail.lstrip(": ")))
        tail = tail.rstrip(".!?").strip()
        tail = re.sub(r"^" + _OBJECT + r"(?:\s+|$)", "", tail, count=1, flags=re.I)
        if action == "translation":
            target = re.fullmatch(
                r"(?:на|to|into|in)\s+(русский|английский|russian|english|ru|en)(?:\s+язык)?",
                tail, re.I,
            )
            if target is None:
                raise CommandError("Укажите язык перевода, например «Переведи документ на русский».")
            return Command(action, target_language=_TARGETS[target.group(1).casefold()])
        if tail:
            raise CommandError("Используйте «Сделай реферирование документа» или «Озвучь документ» для выбранного файла.")
        return Command(action)
    raise CommandError("Команда не распознана, обратитесь к странице помощи для списка рабочих команд или попробуйте снова.")
