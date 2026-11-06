"""Процесс Windows: глобальная горячая клавиша и чтение текста через UI Automation.

Обмен с родителем идёт через строки JSON в stdout. Закрытие stdin или команда
stop завершают процесс. COM-объекты остаются в одном потоке собственного процесса.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import sys
from ctypes import wintypes
from threading import Event, Thread
from typing import Any

HOTKEY_ID = 1
HOTKEY_MODIFIERS = 0x0001 | 0x0002 | 0x4000  # Alt, Ctrl и запрет автоповтора.
HOTKEY_KEY = 0x77  # F8.
WM_HOTKEY = 0x0312
MAX_TEXT_LENGTH = 20_000


class CaptureFailure(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class WindowsDesktop:
    """Ограничивает обращения к Win32 координатами, заголовком окна и горячей клавишей."""

    def __init__(self) -> None:
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.RegisterHotKey.argtypes = (
            wintypes.HWND,
            ctypes.c_int,
            wintypes.UINT,
            wintypes.UINT,
        )
        self._user32.RegisterHotKey.restype = wintypes.BOOL
        self._user32.UnregisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int)
        self._user32.UnregisterHotKey.restype = wintypes.BOOL
        self._user32.PeekMessageW.argtypes = (
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
            wintypes.UINT,
        )
        self._user32.PeekMessageW.restype = wintypes.BOOL
        self._user32.GetPhysicalCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
        self._user32.GetPhysicalCursorPos.restype = wintypes.BOOL
        self._user32.WindowFromPoint.argtypes = (wintypes.POINT,)
        self._user32.WindowFromPoint.restype = wintypes.HWND
        self._user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
        self._user32.GetAncestor.restype = wintypes.HWND
        self._user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        self._user32.GetWindowTextW.restype = ctypes.c_int

    def register(self) -> None:
        if not self._user32.RegisterHotKey(None, HOTKEY_ID, HOTKEY_MODIFIERS, HOTKEY_KEY):
            raise CaptureFailure("hotkey_busy")

    def unregister(self) -> None:
        self._user32.UnregisterHotKey(None, HOTKEY_ID)

    def hotkey_pressed(self) -> bool:
        message = wintypes.MSG()
        pressed = False
        while self._user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
            pressed = pressed or (message.message == WM_HOTKEY and message.wParam == HOTKEY_ID)
        return pressed

    def cursor_position(self) -> tuple[int, int]:
        point = wintypes.POINT()
        if not self._user32.GetPhysicalCursorPos(ctypes.byref(point)):
            raise CaptureFailure("capture_failed")
        return point.x, point.y

    def window_title(self, x: int, y: int) -> str:
        window = self._user32.WindowFromPoint(wintypes.POINT(x, y))
        window = self._user32.GetAncestor(window, 2)
        title = ctypes.create_unicode_buffer(257)
        self._user32.GetWindowTextW(window, title, len(title))
        return title.value or "Другое приложение Windows"


class UIAutomationTextReader:
    """Читает слово или абзац, не меняя фокус, выделение и буфер обмена."""

    def __init__(self) -> None:
        # comtypes инициализирует COM при импорте. Процесс не содержит UI-потоков,
        # поэтому заранее выбираем требуемую для UI Automation модель MTA.
        sys.coinit_flags = 0
        try:
            import comtypes
            import comtypes.client
        except ImportError as error:
            raise CaptureFailure("missing_dependency") from error
        self._com_error = comtypes.COMError
        try:
            self._uia = comtypes.client.GetModule("UIAutomationCore.dll")
            self._client = comtypes.client.CreateObject(
                self._uia.CUIAutomation8, interface=self._uia.IUIAutomation2
            )
            self._client.ConnectionTimeout = 2000
            self._client.TransactionTimeout = 2000
            self._walker = self._client.RawViewWalker
        except (OSError, comtypes.COMError) as error:
            raise CaptureFailure("automation_unavailable") from error

    def read_at(self, x: int, y: int, unit: str) -> str:
        if unit not in ("word", "paragraph"):
            raise CaptureFailure("capture_failed")
        point = self._uia.tagPOINT(x, y)
        element = self._client.ElementFromPoint(point)
        text_unit = self._uia.TextUnit_Word if unit == "word" else self._uia.TextUnit_Paragraph
        for _ in range(16):
            if not element:
                break
            if element.CurrentIsPassword:
                raise CaptureFailure("password")
            try:
                pattern = element.GetCurrentPattern(self._uia.UIA_TextPatternId)
                if pattern:
                    pattern = pattern.QueryInterface(self._uia.IUIAutomationTextPattern)
                    text_range = pattern.RangeFromPoint(point)
                    text_range.ExpandToEnclosingUnit(text_unit)
                    if contains_point(text_range.GetBoundingRectangles(), x, y):
                        text = text_range.GetText(MAX_TEXT_LENGTH + 1)
                        if len(text) > MAX_TEXT_LENGTH:
                            raise CaptureFailure("too_long")
                        if text.strip():
                            return text
            except self._com_error:
                # У текстового листа может не быть TextPattern: ищем его у контейнера.
                pass
            element = self._walker.GetParentElement(element)
        raise CaptureFailure("no_text")


def contains_point(rectangles: Any, x: int, y: int) -> bool:
    """RangeFromPoint ищет ближайший текст; проверка исключает соседний с ним фон."""
    if rectangles is None:
        return False
    for index in range(0, len(rectangles) - 3, 4):
        left, top, width, height = rectangles[index : index + 4]
        if width > 0 and height > 0 and left - 1 <= x <= left + width + 1:
            if top - 1 <= y <= top + height + 1:
                return True
    return False


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def wait_for_stop(stopped: Event) -> None:
    """EOF означает, что родитель завершился или закрыл сессию."""
    try:
        for line in sys.stdin:
            if line.strip() == "stop":
                break
    finally:
        stopped.set()


def listen(unit: str) -> int:
    desktop = WindowsDesktop()
    registered = False
    stopped = Event()
    try:
        reader = UIAutomationTextReader()
        desktop.register()
        registered = True
        Thread(target=wait_for_stop, args=(stopped,), daemon=True).start()
        emit({"type": "ready"})
        while not stopped.wait(0.05):
            if not desktop.hotkey_pressed():
                continue
            try:
                x, y = desktop.cursor_position()
                text = reader.read_at(x, y, unit)
                emit({"type": "captured", "text": text, "source": desktop.window_title(x, y)})
            except CaptureFailure as error:
                emit({"type": "error", "code": error.code})
            except Exception:
                emit({"type": "error", "code": "capture_failed"})
        return 0
    except CaptureFailure as error:
        emit({"type": "error", "code": error.code})
        return 1
    except Exception:
        emit({"type": "error", "code": "automation_unavailable"})
        return 1
    finally:
        if registered:
            desktop.unregister()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--unit", choices=("word", "paragraph"), required=True)
    arguments = parser.parse_args()
    if sys.platform != "win32":
        return 1
    return listen(arguments.unit)


if __name__ == "__main__":
    raise SystemExit(main())
