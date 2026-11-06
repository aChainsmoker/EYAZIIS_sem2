"""Библиотека без кеша: отдельная папка для книги и TXT-файл для каждой главы."""

import json
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from literary_voice.application.text import decode_text_file
from literary_voice.domain.errors import LibraryError
from literary_voice.domain.library import Book, Chapter, LibrarySnapshot

MAX_CHAPTER_BYTES = 1_000_000
MAX_METADATA_BYTES = 64_000


def _natural_key(value: str) -> tuple[tuple[int, int | str], ...]:
    """Располагает главу 2 перед главой 10, даже если в именах нет ведущих нулей."""
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in re.split(r"(\d+)", value)
    )


def _is_visible(path: Path) -> bool:
    return not path.name.startswith((".", "~"))


def _is_link(path: Path) -> bool:
    """Исключает также точки соединения Windows, не определяемые Path.is_symlink."""
    if path.is_symlink():
        return True
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


class FileSystemLibraryRepository:
    """При каждой операции читает данные непосредственно из исходной папки.

    Необязательный файл ``book.json`` содержит только сведения для отображения.
    Список глав определяется имеющимися TXT-файлами, поэтому при добавлении
    или удалении главы не требуется обновлять отдельный перечень. Символические
    ссылки и точки соединения Windows исключаются.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

    def scan(self) -> LibrarySnapshot:
        issues: list[str] = []
        try:
            folders = sorted(self.root.iterdir(), key=lambda path: _natural_key(path.name))
        except FileNotFoundError:
            return LibrarySnapshot(())
        except OSError:
            return LibrarySnapshot((), ("Не удалось открыть папку «Литература».",))

        books: list[Book] = []
        for folder in folders:
            try:
                if not _is_visible(folder) or _is_link(folder) or not folder.is_dir():
                    continue
                book = self._scan_book(folder, issues)
                if book is not None:
                    books.append(book)
            except FileNotFoundError:
                # Редактор или файловый менеджер может удалить объект между двумя вызовами stat.
                continue
            except OSError:
                issues.append(f"Не удалось прочитать произведение «{folder.name}».")
        return LibrarySnapshot(tuple(books), tuple(issues))

    def _scan_book(self, folder: Path, issues: list[str]) -> Book | None:
        chapters: list[Chapter] = []
        for path in sorted(folder.iterdir(), key=lambda item: _natural_key(item.name)):
            try:
                if (
                    not _is_visible(path)
                    or path.suffix.lower() != ".txt"
                    or _is_link(path)
                    or not path.is_file()
                ):
                    continue
                info = path.stat()
            except FileNotFoundError:
                continue
            except OSError:
                issues.append(f"Не удалось проверить главу «{folder.name}/{path.name}».")
                continue
            relative_path = path.relative_to(self.root).as_posix()
            chapters.append(
                Chapter(
                    id=relative_path,
                    book_id=folder.name,
                    title=path.stem,
                    relative_path=relative_path,
                    revision=f"{info.st_mtime_ns}:{info.st_size}",
                )
            )
        if not chapters:
            return None

        metadata = self._read_metadata(folder, issues)
        fallback_author, separator, fallback_title = folder.name.partition(" - ")
        if not separator:
            fallback_title, fallback_author = folder.name, "Автор не указан"
        year = metadata.get("year")
        source_url = self._text_metadata(metadata, "source_url", "")
        try:
            valid_source = urlsplit(source_url).scheme in {"http", "https"}
        except ValueError:
            valid_source = False
        if not valid_source:
            source_url = ""
        return Book(
            id=folder.name,
            title=self._text_metadata(metadata, "title", fallback_title),
            author=self._text_metadata(metadata, "author", fallback_author),
            chapters=tuple(chapters),
            source_url=source_url,
            year=year if type(year) is int else None,
        )

    @staticmethod
    def _text_metadata(metadata: dict[str, Any], key: str, default: str) -> str:
        value = metadata.get(key)
        return value.strip() if isinstance(value, str) and value.strip() else default

    @staticmethod
    def _read_metadata(folder: Path, issues: list[str]) -> dict[str, Any]:
        path = folder / "book.json"
        try:
            if not path.exists():
                return {}
            if _is_link(path):
                return {}
            with path.open("rb") as stream:
                data = stream.read(MAX_METADATA_BYTES + 1)
            if len(data) > MAX_METADATA_BYTES:
                raise ValueError("metadata size limit exceeded")
            metadata = json.loads(data.decode("utf-8-sig"))
            if not isinstance(metadata, dict):
                raise ValueError("metadata must be a JSON object")
        except FileNotFoundError:
            return {}
        except (OSError, UnicodeError, ValueError):
            issues.append(
                f"Не удалось прочитать book.json для «{folder.name}». Используется имя папки."
            )
            return {}
        return metadata

    def read_chapter(self, chapter_id: str) -> str:
        path = self._chapter_path(chapter_id)
        try:
            with path.open("rb") as stream:
                data = stream.read(MAX_CHAPTER_BYTES + 1)
        except FileNotFoundError as error:
            raise LibraryError("Глава удалена или перемещена. Выберите другую главу.") from error
        except OSError as error:
            raise LibraryError("Не удалось открыть главу. Проверьте доступ к файлу.") from error
        return decode_text_file(data, max_bytes=MAX_CHAPTER_BYTES)

    def _chapter_path(self, chapter_id: str) -> Path:
        if not isinstance(chapter_id, str) or "\\" in chapter_id or ":" in chapter_id:
            raise LibraryError("Некорректный путь к главе.")
        relative = PurePosixPath(chapter_id)
        if (
            relative.is_absolute()
            or len(relative.parts) != 2
            or any(part in {".", ".."} or part.startswith((".", "~")) for part in relative.parts)
            or relative.suffix.lower() != ".txt"
        ):
            raise LibraryError("Некорректный путь к главе.")
        candidate = self.root.joinpath(*relative.parts)
        try:
            if _is_link(candidate.parent) or _is_link(candidate):
                raise LibraryError("Ссылки на файлы вне библиотеки не поддерживаются.")
            resolved = candidate.resolve(strict=True)
            if not resolved.is_relative_to(self.root) or not resolved.is_file():
                raise LibraryError("Глава должна находиться внутри папки «Литература».")
        except FileNotFoundError as error:
            raise LibraryError("Глава удалена или перемещена. Выберите другую главу.") from error
        except OSError as error:
            raise LibraryError("Не удалось проверить доступ к главе.") from error
        return resolved
