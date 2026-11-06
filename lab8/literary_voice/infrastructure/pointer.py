"""Управление изолированным процессом захвата текста Windows UI Automation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from queue import Empty, Full, Queue
from threading import RLock, Thread
from typing import Any

from literary_voice.domain.capture import CapturedText, CaptureEvent, CaptureUnit
from literary_voice.domain.errors import CaptureError

_ERROR_MESSAGES = {
    "missing_dependency": "Установите зависимости приложения: необходим пакет comtypes.",
    "hotkey_busy": (
        "Ctrl+Alt+F8 уже используется. Отключите захват в другой вкладке или приложении "
        "и попробуйте ещё раз."
    ),
    "automation_unavailable": "Не удалось подключиться к Windows UI Automation.",
    "no_text": (
        "Под указателем нет доступного текста. Наведите мышь на буквы в браузере "
        "или текстовом редакторе и повторите Ctrl+Alt+F8. "
        "Текст на картинках и в сканах не поддерживается."
    ),
    "password": "Захват текста из поля пароля отключён.",
    "too_long": "Абзац длиннее 20 000 символов. Выберите захват слова или другой абзац.",
    "capture_failed": "Приложение не предоставило текст. Попробуйте другой участок или окно.",
    "invalid_response": "Компонент захвата вернул некорректный ответ. Выключите и включите захват.",
    "worker_stopped": "Компонент захвата завершился. Включите захват повторно.",
}


class WindowsPointerCapture:
    """Один экземпляр принадлежит одной сессии; фоновые потоки не вызывают Streamlit."""

    def __init__(self, startup_timeout: float = 12.0) -> None:
        self._startup_timeout = startup_timeout
        self._process: subprocess.Popen[str] | None = None
        self._reader: Thread | None = None
        self._events: Queue[dict[str, Any]] = Queue(maxsize=8)
        self._lock = RLock()

    @property
    def running(self) -> bool:
        with self._lock:
            return self._process is not None and self._process.poll() is None

    def start(self, unit: CaptureUnit) -> None:
        if sys.platform != "win32":
            raise CaptureError("Захват под указателем доступен при локальном запуске в Windows.")
        with self._lock:
            if self.running:
                return
            self.stop()
            command = [
                sys.executable,
                str(Path(__file__).with_name("pointer_worker.py")),
                "--unit",
                unit.value,
            ]
            try:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            except OSError as error:
                raise CaptureError("Не удалось запустить компонент захвата Windows.") from error
            self._process = process
            self._reader = Thread(target=self._read_events, args=(process,), daemon=True)
            self._reader.start()
            try:
                response = self._events.get(timeout=self._startup_timeout)
            except Empty as error:
                self.stop()
                raise CaptureError(
                    "Компонент захвата не ответил вовремя. Попробуйте ещё раз."
                ) from error
            if response.get("type") != "ready":
                self.stop()
                raise CaptureError(self._error_message(response))

    def stop(self) -> None:
        with self._lock:
            process, self._process = self._process, None
            if process is not None:
                try:
                    if process.stdin is not None:
                        process.stdin.write("stop\n")
                        process.stdin.flush()
                    process.wait(timeout=1)
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    if process.poll() is None:
                        process.kill()
                    process.wait(timeout=2)
                finally:
                    if process.stdin is not None:
                        try:
                            process.stdin.close()
                        except OSError:
                            pass
                if self._reader is not None:
                    self._reader.join(timeout=1)
                if process.stdout is not None:
                    process.stdout.close()
            self._reader = None
            self._clear_events()

    def poll(self) -> CaptureEvent | None:
        with self._lock:
            try:
                response = self._events.get_nowait()
            except Empty:
                if self._process is not None and not self.running:
                    self.stop()
                    return CaptureEvent(error=_ERROR_MESSAGES["worker_stopped"])
                return None
            if response.get("type") == "captured":
                text, source = response.get("text"), response.get("source")
                if isinstance(text, str) and 0 < len(text) <= 20_000 and isinstance(source, str):
                    return CaptureEvent(result=CapturedText(text, source[:256]))
                return CaptureEvent(error=_ERROR_MESSAGES["invalid_response"])
            return CaptureEvent(error=self._error_message(response))

    def _read_events(self, process: subprocess.Popen[str]) -> None:
        if process.stdout is None:
            return
        try:
            while line := process.stdout.readline(200_000):
                try:
                    response = json.loads(line)
                    if not isinstance(response, dict):
                        raise ValueError("Expected an object")
                except (ValueError, TypeError):
                    response = {"type": "error", "code": "invalid_response"}
                self._publish(response)
        except (OSError, ValueError, UnicodeError):
            pass
        finally:
            self._publish({"type": "error", "code": "worker_stopped"})

    def _publish(self, response: dict[str, Any]) -> None:
        try:
            self._events.put_nowait(response)
        except Full:
            try:
                self._events.get_nowait()
            except Empty:
                pass
            self._events.put_nowait(response)

    def _clear_events(self) -> None:
        while True:
            try:
                self._events.get_nowait()
            except Empty:
                return

    @staticmethod
    def _error_message(response: dict[str, Any]) -> str:
        code = response.get("code")
        if not isinstance(code, str):
            return _ERROR_MESSAGES["invalid_response"]
        return _ERROR_MESSAGES.get(code, _ERROR_MESSAGES["capture_failed"])
