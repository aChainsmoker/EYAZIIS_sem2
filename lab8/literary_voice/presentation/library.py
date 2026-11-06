"""Автообновляемое представление файловой библиотеки, не затрагивающее плеер."""

import streamlit as st

from literary_voice.application.chapters import split_chapter
from literary_voice.application.library import LibraryService
from literary_voice.domain.errors import ReadingError


def _select_existing(key: str, identifiers: list[str]) -> None:
    """Удалённый или переименованный файл не должен оставаться выбранным в виджете."""
    if st.session_state.get(key) not in identifiers:
        st.session_state[key] = identifiers[0] if identifiers else None


@st.fragment(run_every="1s")
def render_library(service: LibraryService) -> None:
    st.subheader("Английская классика")
    st.caption(
        "Книги и главы из папки «Литература». Добавления, изменения и удаления "
        "отображаются автоматически, проверка каждую секунду."
    )
    snapshot = service.scan()
    if snapshot.issues:
        with st.expander("Некоторые файлы не удалось прочитать"):
            for issue in snapshot.issues:
                st.warning(issue)
    books = {book.id: book for book in snapshot.books}
    _select_existing("library_book_id", list(books))
    if not books:
        _select_existing("library_chapter_id", [])
        st.info(
            "Библиотека пуста. Создайте в папке «Литература» папку произведения "
            "и добавьте в неё главы в формате TXT."
        )
        return

    chapter_count = sum(len(book.chapters) for book in books.values())
    st.caption(f"Произведений: {len(books)} · глав: {chapter_count}")
    book_id = st.selectbox(
        "Произведение",
        options=list(books),
        format_func=lambda identifier: f"{books[identifier].author} — {books[identifier].title}",
        key="library_book_id",
    )
    book = books[book_id]
    chapters = {chapter.id: chapter for chapter in book.chapters}
    _select_existing("library_chapter_id", list(chapters))
    chapter_id = st.selectbox(
        "Глава",
        options=list(chapters),
        format_func=lambda identifier: chapters[identifier].title,
        key="library_chapter_id",
    )
    chapter = chapters[chapter_id]
    st.caption(f"{book.author}" + (f" · {book.year}" if book.year else ""))
    if book.source_url:
        st.link_button("Источник произведения", book.source_url)

    try:
        parts = split_chapter(service.read_chapter(chapter.id))
    except ReadingError as error:
        st.error(str(error))
        return

    source_revision = (chapter.id, chapter.revision)
    if st.session_state.get("library_part_source") != source_revision:
        st.session_state["library_part_source"] = source_revision
        st.session_state["library_part_index"] = 0
    if st.session_state.get("library_part_index", 0) not in range(len(parts)):
        st.session_state["library_part_index"] = 0

    if len(parts) > 1:
        st.info(
            f"Глава сохранена целиком. Для озвучивания она разделена на {len(parts)} "
            "фрагмента до 20 000 символов. Все фрагменты доступны ниже."
        )
        part_index = st.selectbox(
            "Фрагмент главы",
            options=list(range(len(parts))),
            format_func=lambda index: (
                f"{index + 1} из {len(parts)} · {len(parts[index]):,} символов"
            ),
            key="library_part_index",
        )
    else:
        part_index = 0
    selected_text = parts[part_index].strip()
    st.caption(f"{chapter.relative_path} · {len(selected_text):,} символов для чтения")

    if st.button("Открыть для чтения", key="load_chapter", type="primary"):
        label = f"{book.title} · {chapter.title}"
        if len(parts) > 1:
            label += f" · фрагмент {part_index + 1}/{len(parts)}"
        # Редактор находится вне фрагмента. Его значение применяется в начале
        # полного перезапуска скрипта, до создания соответствующего виджета.
        st.session_state["pending_library_text"] = (selected_text, label)
        st.rerun()
    with st.expander("Предпросмотр текста"):
        st.text(selected_text)
