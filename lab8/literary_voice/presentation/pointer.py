"""Управление захватом текста и доставка результата в редактор Streamlit."""

import streamlit as st

from literary_voice.application.capture import PointerCaptureService
from literary_voice.composition import create_pointer_capture_service
from literary_voice.domain.capture import CaptureUnit
from literary_voice.domain.errors import ReadingError

_UNIT_LABELS = {CaptureUnit.PARAGRAPH: "Абзац", CaptureUnit.WORD: "Слово"}


def _release_capture(service: PointerCaptureService) -> None:
    service.stop()


@st.cache_resource(scope="session", on_release=_release_capture, show_spinner=False)
def get_capture_service() -> PointerCaptureService:
    """Ресурс сессии переживает перезапуски; её закрытие освобождает горячую клавишу."""
    return create_pointer_capture_service()


@st.fragment(run_every="1s")
def render_pointer_capture() -> None:
    with st.expander("Текст под указателем мыши"):
        st.caption(
            "Включите захват, наведите мышь на текст в другом окне и нажмите Ctrl+Alt+F8. "
            "Текст заменит содержимое редактора; затем нажмите «Озвучить текст». "
            "Работает на этом компьютере при локальном запуске в Windows."
        )
        service = get_capture_service()
        unit = st.selectbox(
            "Что захватывать",
            options=list(_UNIT_LABELS),
            format_func=_UNIT_LABELS.__getitem__,
            key="capture_unit",
            disabled=service.running,
        )
        start, stop = st.columns(2)
        if start.button("Включить захват", key="capture_start", disabled=service.running):
            try:
                with st.spinner("Подключаем захват Windows…"):
                    service.start(unit)
                st.session_state.pop("capture_error", None)
                st.rerun()
            except ReadingError as error:
                st.session_state["capture_error"] = str(error)
        if stop.button("Выключить захват", key="capture_stop", disabled=not service.running):
            service.stop()
            st.session_state.pop("capture_error", None)
            st.rerun()

        event = service.poll()
        if event is not None:
            if event.result is not None:
                st.session_state.pop("capture_error", None)
                st.session_state["pending_capture_text"] = event.result
                st.rerun()
            elif event.error:
                st.session_state["capture_error"] = event.error
        if service.running:
            st.success("Захват включён · Ctrl+Alt+F8")
        else:
            st.caption("Захват выключен.")
        if error := st.session_state.get("capture_error"):
            st.warning(error)
