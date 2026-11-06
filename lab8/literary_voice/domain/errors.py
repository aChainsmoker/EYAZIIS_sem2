"""Ошибки, которые можно показать пользователю без трассировки исключения."""


class ReadingError(Exception):
    """Базовый класс ошибок приложения, после которых работу можно продолжить."""


class ValidationError(ReadingError):
    """Введённый текст или настройки озвучивания некорректны."""


class EngineUnavailableError(ReadingError):
    """Синтезатор или необходимые голоса недоступны."""


class SynthesisError(ReadingError):
    """Выбранный синтезатор не смог создать аудиозапись."""


class LibraryError(ReadingError):
    """Выбранный элемент библиотеки сейчас невозможно прочитать."""


class CaptureError(ReadingError):
    """Не удалось получить текст под указателем в другом приложении."""
