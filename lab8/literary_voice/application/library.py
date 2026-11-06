"""Сценарии библиотеки с внедряемым хранилищем, не зависящие от файлового API."""

from literary_voice.domain.library import LibraryRepository, LibrarySnapshot


class LibraryService:
    def __init__(self, repository: LibraryRepository) -> None:
        self._repository = repository

    def scan(self) -> LibrarySnapshot:
        return self._repository.scan()

    def read_chapter(self, chapter_id: str) -> str:
        return self._repository.read_chapter(chapter_id)
