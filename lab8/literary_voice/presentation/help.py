"""Отображение инструкции пользователя из Markdown-ресурсов пакета."""

from importlib.resources import files

import streamlit as st

_HELP_CONTENT = files("literary_voice.presentation").joinpath("help_content")
_HELP_SECTIONS = (
    "usage.md",
    "pointer_capture.md",
    "library.md",
    "speech_modes.md",
    "settings.md",
)


def render_help() -> None:
    """Выводит разделы справки и раскрываемые рекомендации по устранению ошибок."""
    for filename in _HELP_SECTIONS:
        st.markdown(_HELP_CONTENT.joinpath(filename).read_text(encoding="utf-8"))

    with st.expander("Если что-то не работает"):
        st.markdown(_HELP_CONTENT.joinpath("troubleshooting.md").read_text(encoding="utf-8"))
