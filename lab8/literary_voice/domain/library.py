"""Неизменяемые снимки библиотеки и контракт поиска локальных глав."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Chapter:
    id: str
    book_id: str
    title: str
    relative_path: str
    revision: str


@dataclass(frozen=True)
class Book:
    id: str
    title: str
    author: str
    chapters: tuple[Chapter, ...]
    source_url: str = ""
    year: int | None = None


@dataclass(frozen=True)
class LibrarySnapshot:
    books: tuple[Book, ...]
    issues: tuple[str, ...] = ()


class LibraryRepository(Protocol):
    def scan(self) -> LibrarySnapshot:
        """Создаёт актуальный снимок книг и глав, находящихся на диске."""
        ...

    def read_chapter(self, chapter_id: str) -> str:
        """Читает текущий полный текст главы или вызывает исключение ReadingError."""
        ...
