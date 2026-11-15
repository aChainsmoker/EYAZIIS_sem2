from dataclasses import dataclass, field
from typing import Literal

Action = Literal["search", "summary", "translation", "speech"]


@dataclass(frozen=True)
class Command:
    action: Action
    argument: str = ""
    target_language: Literal["ru", "en"] | None = None


@dataclass(frozen=True)
class BotResult:
    success: bool
    action: Action | None
    page: Action | None
    message: str
    data: dict = field(default_factory=dict)
    error_code: str | None = None
