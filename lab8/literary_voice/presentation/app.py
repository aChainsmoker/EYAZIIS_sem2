"""Экраны Streamlit и обработчики сессии; прикладные правила находятся в application/."""

import logging
import re
from dataclasses import dataclass

import streamlit as st

from literary_voice.application.service import ReadingService
from literary_voice.application.text import TextProcessor, decode_text_file
from literary_voice.composition import (
    ENGINE_LABELS,
    create_engine,
    create_library_service,
    default_engine_id,
)
from literary_voice.domain.errors import ReadingError
from literary_voice.domain.models import ReadingResult, SpeechSettings, Voice
from literary_voice.presentation.help import render_help
from literary_voice.presentation.library import render_library
from literary_voice.presentation.pointer import render_pointer_capture

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Playback:
    """Хранит подписи и настройки, относящиеся к созданной аудиозаписи."""

    result: ReadingResult
    voice_label: str
    engine_label: str


@st.cache_data(ttl=600, show_spinner=False)
def load_voices(engine_id: str) -> tuple[Voice, ...]:
    # Общими являются только сведения о голосах; текст и аудио остаются в session_state.
    return ReadingService(create_engine(engine_id)).list_voices()


def _initialize_state() -> None:
    st.session_state.setdefault("editor_text", "")
    st.session_state.setdefault("engine_id", default_engine_id())
    st.session_state.setdefault("playback", None)
    st.session_state.setdefault("notice", None)
    pending = st.session_state.pop("pending_library_text", None)
    if pending is not None:
        text, label = pending
        st.session_state["editor_text"] = text
        st.session_state["notice"] = ("success", f"В редакторе: {label}.")
        st.session_state["main_tabs"] = "Озвучивание"
    captured = st.session_state.pop("pending_capture_text", None)
    if captured is not None:
        st.session_state["editor_text"] = captured.text
        st.session_state["notice"] = ("success", f"Текст под указателем: {captured.source}.")
        st.session_state["main_tabs"] = "Озвучивание"


def _show_library() -> None:
    st.session_state["main_tabs"] = "Библиотека"


def _clear_editor() -> None:
    st.session_state["editor_text"] = ""


def _import_text() -> None:
    uploaded = st.session_state.get("text_file")
    if uploaded is None:
        return
    try:
        text = decode_text_file(uploaded.getvalue())
        text = TextProcessor().prepare(text)
    except ReadingError as error:
        st.session_state["notice"] = ("error", str(error))
    else:
        st.session_state["editor_text"] = text
        st.session_state["notice"] = ("success", f"Загружен файл: {uploaded.name}.")


def _voice_label(voice: Voice) -> str:
    gender = {"Female": "женский", "Male": "мужской"}.get(voice.gender, voice.gender)
    return " · ".join(part for part in (voice.name, voice.locale, gender) if part)


def _render_settings() -> tuple[str, tuple[Voice, ...], SpeechSettings | None]:
    with st.sidebar:
        st.header("Голос и чтение")
        engine_id = st.selectbox(
            "Режим синтеза",
            options=list(ENGINE_LABELS),
            format_func=ENGINE_LABELS.__getitem__,
            key="engine_id",
        )
        if engine_id == "sapi":
            st.caption("Без интернета · аудио WAV")
        else:
            st.caption("Интернет · аудио MP3 · текст отправляется Microsoft")

        st.button("Обновить голоса", on_click=load_voices.clear, width="stretch")
        voices: tuple[Voice, ...] = ()
        try:
            with st.spinner("Получаем английские голоса…"):
                voices = load_voices(engine_id)
        except ReadingError as error:
            st.warning(str(error))

        if not voices:
            st.info("Английские голоса недоступны. Выберите другой режим или откройте «Помощь».")
        voice_by_id = {voice.id: voice for voice in voices}
        british_index = next(
            (index for index, voice in enumerate(voices) if voice.locale == "en-GB"), 0
        )
        voice_id = st.selectbox(
            "Английский голос",
            options=list(voice_by_id),
            index=british_index if voices else None,
            format_func=lambda identifier: _voice_label(voice_by_id[identifier]),
            key=f"voice_{engine_id}",
            disabled=not voices,
            placeholder="Нет доступных голосов",
        )
        rate = st.slider(
            "Темп, %",
            min_value=-50,
            max_value=100,
            value=0,
            step=5,
            key="speech_rate",
            help="0 — обычный темп; отрицательные значения замедляют чтение.",
        )
        volume = st.slider("Громкость, %", 0, 100, 85, step=5, key="speech_volume")
        if volume == 0:
            st.warning("Громкость 0 %: создаваемая запись будет беззвучной.")
        st.divider()
        st.caption("Изменили настройки? Нажмите «Озвучить текст» ещё раз.")
    settings = SpeechSettings(voice_id, rate, volume) if voice_id else None
    return engine_id, voices, settings


def _render_editor() -> str:
    st.subheader("Текст произведения")
    st.caption("Вставьте английский текст или выберите произведение и главу из библиотеки.")
    st.button("Выбрать книгу и главу", on_click=_show_library)
    render_pointer_capture()
    text = st.text_area(
        "Английский текст",
        key="editor_text",
        height=310,
        placeholder="Paste an excerpt from an English classic…",
        help="Ctrl+V — вставить из буфера. До 20 000 символов после нормализации.",
    )
    words = len(re.findall(r"\b[\w’'-]+\b", text))
    st.caption(f"{len(text):,} символов · {words:,} слов · язык озвучивания: English")
    with st.expander("Загрузить TXT или очистить редактор"):
        st.file_uploader(
            "Текстовый файл",
            type=["txt"],
            key="text_file",
            on_change=_import_text,
            help="UTF-8 или UTF-16 с BOM, до 1 000 000 байт.",
        )
        st.button("Очистить редактор", on_click=_clear_editor)
    notice = st.session_state.pop("notice", None)
    if notice:
        kind, message = notice
        if kind == "error":
            st.error(message)
        else:
            st.success(message)
    return text


def _is_current(
    playback: Playback, text: str, engine_id: str, settings: SpeechSettings | None
) -> bool:
    try:
        prepared = TextProcessor().prepare(text)
    except ReadingError:
        return False
    result = playback.result
    return prepared == result.text and engine_id == result.engine_id and settings == result.settings


def _render_playback(text: str, engine_id: str, settings: SpeechSettings | None) -> None:
    playback: Playback | None = st.session_state["playback"]
    st.subheader("Запись")
    if playback is None:
        st.info("Готовая запись появится здесь после озвучивания.")
        return
    result = playback.result
    if _is_current(playback, text, engine_id, settings):
        st.success("Запись соответствует текущему тексту и настройкам.")
    else:
        st.warning("Текст или настройки изменились. Озвучьте текст заново, чтобы обновить запись.")
    st.audio(result.audio.data, format=result.audio.mime_type)
    st.caption(
        f"{playback.engine_label} · {playback.voice_label}\n\n"
        f"Темп {result.settings.rate:+d} % · громкость {result.settings.volume} % · "
        f"{len(result.text):,} символов · {len(result.audio.data) / 1024:.0f} КБ"
    )
    stamp = result.created_at.strftime("%Y%m%d_%H%M%S")
    st.download_button(
        "Скачать запись",
        data=result.audio.data,
        file_name=f"literary_voice_{stamp}.{result.audio.extension.lstrip('.')}",
        mime=result.audio.mime_type,
        on_click="ignore",
        width="stretch",
    )
    with st.expander("Текст этой записи"):
        st.text(result.text)


def _render_reader(
    engine_id: str, voices: tuple[Voice, ...], settings: SpeechSettings | None
) -> None:
    editor_column, audio_column = st.columns([1.4, 1], gap="large")
    with editor_column:
        text = _render_editor()
        synthesize = st.button(
            "Озвучить текст",
            type="primary",
            key="synthesize",
            disabled=settings is None or not text.strip(),
            width="stretch",
        )
        if synthesize and settings is not None:
            try:
                service = ReadingService(create_engine(engine_id), voices=voices)
                with st.spinner("Создаём запись. Пожалуйста, дождитесь завершения…"):
                    result = service.synthesize(text, settings)
                voice = next(voice for voice in voices if voice.id == settings.voice_id)
                st.session_state["playback"] = Playback(
                    result=result,
                    voice_label=_voice_label(voice),
                    engine_label=ENGINE_LABELS[engine_id],
                )
            except ReadingError as error:
                st.error(str(error))
            except Exception:
                logger.exception("Unexpected speech synthesis failure")
                st.error("Не удалось создать запись. Попробуйте ещё раз или выберите другой режим.")
    with audio_column:
        _render_playback(text, engine_id, settings)


def main() -> None:
    st.set_page_config(page_title="Literary Voice", page_icon="📖", layout="wide")
    _initialize_state()
    st.title("Literary Voice")
    st.caption("Классическая английская литература · чтение на английском")
    engine_id, voices, settings = _render_settings()
    reader, library, help_tab = st.tabs(
        ["Озвучивание", "Библиотека", "Помощь"], key="main_tabs", on_change="rerun"
    )
    with reader:
        _render_reader(engine_id, voices, settings)
    with library:
        render_library(create_library_service())
    with help_tab:
        render_help()
