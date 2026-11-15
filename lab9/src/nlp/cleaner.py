import re
import unicodedata


def clean_text(text: str) -> str:
    """Детерминированная очистка из №3; языковая модель не используется."""
    characters = []
    for character in text:
        category = unicodedata.category(character)
        if character in "\r\n\t":
            characters.append(character)
        elif character == "�" or category in {"Cc", "Cf", "Cs", "Co", "Cn", "So"} or 0x1F000 <= ord(character) <= 0x1FAFF:
            characters.append(" ")
        else:
            characters.append(character)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in "".join(characters).splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
