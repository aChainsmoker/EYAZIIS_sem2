import os
import io
import re
import math
import streamlit as st
import pandas as pd
from collections import Counter
from sklearn.feature_extraction.text import CountVectorizer
from pathlib import Path
import database as db
from model import LanguageModel
from controller import AppController
from watcher import FolderWatcher

# ================================================================
#  ИНИЦИАЛИЗАЦИЯ
# ================================================================
WATCH_FOLDER = "synced_folder"
os.makedirs(WATCH_FOLDER, exist_ok=True)
db.init_db()

# Пути к контенту
CONTENT_DIR = Path("content")
TEMPLATES_DIR = Path("templates")

# Загрузка markdown файлов
def load_markdown(filename):
    """Загружает markdown файл"""
    filepath = CONTENT_DIR / filename
    if filepath.exists():
        return filepath.read_text(encoding="utf-8")
    return f" Файл {filename} не найден"

def load_html_template(filename):
    """Загружает HTML шаблон"""
    filepath = TEMPLATES_DIR / filename
    if filepath.exists():
        return filepath.read_text(encoding="utf-8")
    return None

if 'model' not in st.session_state:
    st.session_state.model = LanguageModel(train_dir="train_data")

if 'controller' not in st.session_state:
    st.session_state.controller = AppController(st.session_state.model)

if 'watcher' not in st.session_state:
    st.session_state.watcher = FolderWatcher(WATCH_FOLDER, st.session_state.model)
    st.session_state.watcher.start()

controller = st.session_state.controller

# ================================================================
#  ФУНКЦИЯ ГЕНЕРАЦИИ HTML-ОТЧЁТА
# ================================================================
def generate_printable_html(df, processed_df, stats_df, selected_doc=None):
    """Генерирует HTML-отчёт используя шаблон"""
    from datetime import datetime
    now = datetime.now().strftime('%d.%m.%Y %H:%M')
    
    # Загружаем шаблон
    template = load_html_template("report.html")
    if not template:
        st.error("Шаблон отчёта не найден!")
        return ""
    
    # Генерация строк таблицы документов
    table_rows = ""
    for i, (_, row) in enumerate(df.iterrows(), 1):
        table_rows += f"""
            <tr>
                <td>{i}</td>
                <td>{row['Имя файла']}</td>
                <td>{row['Источник']}</td>
                <td>{row['Частотные слова']}</td>
                <td>{row['Короткие слова']}</td>
                <td>{row['Нейросеть']}</td>
                <td><strong>{row['Итоговый язык']}</strong></td>
                <td>{row['Статус']}</td>
            </tr>
        """
    
    # Генерация строк статистики
    stats_rows = ""
    if stats_df is not None and not stats_df.empty:
        for _, row in stats_df.iterrows():
            stats_rows += f"""
                <tr>
                    <td>{row['Метод']}</td>
                    <td>{row['Spanish']}</td>
                    <td>{row['English']}</td>
                    <td>{row['Unknown']}</td>
                </tr>
            """
    
    # Подсчёт статистики
    src_counts = processed_df['Источник'].value_counts() if not processed_df.empty else {}
    
    # Замена плейсхолдеров в шаблоне
    html = template.replace("{{now}}", now)
    html = html.replace("{{table_rows}}", table_rows)
    html = html.replace("{{stats_rows}}", stats_rows)
    html = html.replace("{{total_docs}}", str(len(processed_df)))
    html = html.replace("{{spanish_count}}", str(len(processed_df[processed_df["Итоговый язык"] == "Spanish"])))
    html = html.replace("{{english_count}}", str(len(processed_df[processed_df["Итоговый язык"] == "English"])))
    html = html.replace("{{unknown_count}}", str(len(processed_df[processed_df["Итоговый язык"] == "Unknown"])))
    html = html.replace("{{folder_count}}", str(src_counts.get('folder', 0)))
    html = html.replace("{{frontend_count}}", str(src_counts.get('frontend', 0)))
    
    return html

# ================================================================
#  ВКЛАДКИ
# ================================================================
st.set_page_config(page_title="Распознавание языка (Вар. 18)", layout="wide")
st.title("Автоматическое распознавание языка текста")
st.caption(
    "Методы: частотных слов, коротких слов, нейросетевой"
)

tab_help, tab_analysis = st.tabs(["Помощь", "Анализ текстов"])

# ================================================================
#  ВКЛАДКА 1: ПОМОЩЬ (из markdown файла)
# ================================================================
with tab_help:
    help_content = load_markdown("help.md")
    st.markdown(help_content)
    
    st.divider()
    st.subheader("Детальное описание методов")
    methods_content = load_markdown("methods.md")
    st.markdown(methods_content)

# ================================================================
#  ВКЛАДКА 2: АНАЛИЗ ТЕКСТОВ
# ================================================================
with tab_analysis:
    st.header("Анализ текстов")

    # --- Блок загрузки ---
    st.subheader("Загрузка через интерфейс")
    uploaded_file = st.file_uploader("Выберите PDF-документ", type=["pdf"], key="uploader")

    if uploaded_file is not None:
        with st.spinner("Анализ документа..."):
            results = controller.process_uploaded_file(uploaded_file, WATCH_FOLDER)
        st.success(f"Файл **{uploaded_file.name}** успешно обработан!")

    # --- Информация о папке синхронизации ---
    st.subheader("Синхронизированная папка")
    st.info(
        f"Положите PDF-файлы в папку: `{os.path.abspath(WATCH_FOLDER)}` — "
        "они будут обработаны автоматически (ожидание 3-5 сек). Нажмите 'Обновить данные'."
    )

    # --- Получение данных из БД ---
    docs = controller.get_all_documents()

    if not docs:
        st.warning("База данных пуста. Загрузите файл или добавьте PDF в папку `synced_folder`.")
    else:
        df = pd.DataFrame(
            docs,
            columns=[
                "Имя файла", "Источник", "Частотные слова", "Короткие слова",
                "Нейросеть", "Итоговый язык", "Статус"
            ]
        )

        # НОРМАЛИЗАЦИЯ РЕГИСТРА ЯЗЫКОВ
        lang_columns = ["Частотные слова", "Короткие слова", "Нейросеть", "Итоговый язык"]
        for col in lang_columns:
            df[col] = df[col].apply(
                lambda x: x.capitalize() if isinstance(x, str) and x.lower() != "unknown" else x
            )

        # --- Статус обработки файлов из папки ---
        folder_docs = df[df["Источник"] == "folder"]
        if not folder_docs.empty:
            with st.expander("Статус обработки файлов из папки", expanded=False):
                st.write(folder_docs[["Имя файла", "Статус"]])

        # ============================================================
        #  ТАБЛИЦА 1: Сравнение методов по документам
        # ============================================================
        st.subheader(" Сравнительная таблица результатов по методам")
        st.caption(
            "Каждая строка — документ. Столбцы — результат каждого метода. "
            "Итоговый язык — по голосованию большинства."
        )
        st.dataframe(df, use_container_width=True, hide_index=True)

        # ============================================================
        #  ДЕТАЛЬНЫЙ АНАЛИЗ ПО ТРЁМ МЕТОДАМ (ДАННЫЕ ИЗ БД)
        # ============================================================
        st.subheader(" Детальный анализ выбранного документа")
        st.caption(
            "Сравнительный анализ профилей модели и входного документа по всем трём методам"
        )

        selected_doc = st.selectbox(
            "Выберите документ для детального анализа",
            df["Имя файла"].tolist(),
            key="select_doc_detail"
        )

        if selected_doc:
            doc_path = os.path.join(WATCH_FOLDER, selected_doc)

            if not os.path.exists(doc_path):
                st.error(f"Файл {selected_doc} не найден на диске.")
            else:
                # ========================================================
                #  МЕТОД 1: ЧАСТОТНЫХ СЛОВ (ИЗ БД)
                # ========================================================
                st.markdown("### 1. Метод частотных слов")
                st.caption(
                    "Сравнение частот слов из поискового образа языка (обучающая выборка) "
                    "с частотами в анализируемом документе."
                )

                tabs_freq = st.tabs(["Испанский (Spanish)", "Английский (English)"])

                for idx, lang in enumerate(["spanish", "english"]):
                    with tabs_freq[idx]:
                        freq_data = controller.get_freq_words(selected_doc, lang)
                        if freq_data:
                            freq_df = pd.DataFrame(
                                freq_data,
                                columns=["Слово", "Частота в обучающей выборке", "Частота в документе"]
                            )
                            freq_df = freq_df.sort_values("Частота в документе", ascending=False)
                            st.dataframe(freq_df, use_container_width=True, hide_index=True)

                            total_words = len(freq_df)
                            appeared = (freq_df["Частота в документе"] > 0).sum()
                            st.markdown(
                                f"**Статистика:** всего слов в ПОЯ — **{total_words}**, "
                                f"встречаются в документе — **{appeared} "
                                f"({appeared * 100 // total_words if total_words > 0 else 0}%)**."
                            )
                        else:
                            st.info(f"Нет данных для языка {lang}. Загрузите файл заново.")

                # ========================================================
                #  МЕТОД 2: КОРОТКИХ СЛОВ (ИЗ БД)
                # ========================================================
                st.markdown("### 2. Метод коротких слов (≤5 символов)")
                st.caption(
                    "Вероятности коротких слов в обучающей выборке и вероятности, "
                    "назначенные словам в документе"
                )

                tabs_short = st.tabs(["Испанский (Spanish)", "Английский (English)"])

                for idx, lang in enumerate(["spanish", "english"]):
                    with tabs_short[idx]:
                        short_data = controller.get_short_words(selected_doc, lang)
                        if short_data:
                            short_df = pd.DataFrame(
                                short_data,
                                columns=["Слово", "Вероятность в ПОЯ", "Назначенная вероятность", "Частота в документе"]
                            )
                            st.dataframe(short_df, use_container_width=True, hide_index=True)

                            # Статистика
                            total_short = sum(row[3] for row in short_data)  # сумма doc_freq
                            known = sum(1 for row in short_data if row[1] > 0)  # слова с train_prob > 0
                            unknown = len(short_data) - known

                            st.markdown(
                                f"**Статистика:** всего уникальных коротких слов — **{len(short_data)}**, "
                                f"известных модели (есть в ПОЯ) — **{known}** "
                                f"({known * 100 // len(short_data) if len(short_data) > 0 else 0}%), "
                                f"неизвестных — **{unknown}**."
                            )

                            # Сумма логарифмов
                            import math

                            min_prob = 1e-10
                            log_sum = sum(math.log(row[2]) for row in short_data if row[2] > 0)
                            st.info(
                                f"**Итоговая вероятность (сумма логарифмов):** {log_sum:.2f}\n\n"
                                f"Это значение используется для сравнения языков. "
                                f"Язык с большим значением считается более вероятным."
                            )
                        else:
                            st.info(f"Нет данных для языка {lang}. Загрузите файл заново.")

                # ========================================================
                #  МЕТОД 3: НЕЙРОСЕТЕВОЙ (N-ГРАММЫ ИЗ БД)
                # ========================================================
                st.markdown("### 3. Нейросетевой метод (N-граммы)")
                st.caption("Характерные N-граммы (2-4 символа) в документе")

                ngram_data = controller.get_ngrams(selected_doc)
                if ngram_data:
                    ngram_df = pd.DataFrame(
                        ngram_data,
                        columns=["N-грамма", "Частота в документе"]
                    )
                    st.dataframe(ngram_df.head(50), use_container_width=True, hide_index=True)

                    doc_info = df[df["Имя файла"] == selected_doc].iloc[0]
                    st.info(f"**Предсказание нейросети:** {doc_info['Нейросеть']}")
                else:
                    st.info("Нет данных N-грамм. Загрузите файл заново.")
        # ============================================================
        #  ТАБЛИЦА 2: Сравнительная статистика по методам
        # ============================================================
        st.subheader("Сравнительная статистика методов")
        st.caption("Сколько документов каждый метод отнёс к каждому языку.")

        processed_df = df[df["Статус"] == "processed"].copy()

        if not processed_df.empty:
            methods = ["Частотные слова", "Короткие слова", "Нейросеть"]
            stats_data = []
            for method in methods:
                counts = processed_df[method].value_counts()
                row = {"Метод": method}
                for lang in ["Spanish", "English", "Unknown"]:
                    row[lang] = int(counts.get(lang, 0))
                stats_data.append(row)

            stats_df = pd.DataFrame(stats_data)
            st.dataframe(stats_df, use_container_width=True, hide_index=True)

            spanish_count = stats_df["Spanish"].sum()
            english_count = stats_df["English"].sum()

            if spanish_count > 0 or english_count > 0:
                chart_data = stats_df.set_index("Метод")[["Spanish", "English"]]
                st.bar_chart(chart_data)
            else:
                st.info("Нет распознанных документов для построения графика.")
        else:
            st.info("Нет обработанных документов для построения статистики.")
            stats_df = None

        # ============================================================
        #  СВОДНАЯ СТАТИСТИКА ПО КОЛЛЕКЦИИ
        # ============================================================
        st.subheader("Сводная статистика по коллекции")

        if not processed_df.empty:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Всего документов", len(processed_df))
            col2.metric(
                "Испанский (итог)",
                len(processed_df[processed_df["Итоговый язык"] == "Spanish"]),
            )
            col3.metric(
                "Английский (итог)",
                len(processed_df[processed_df["Итоговый язык"] == "English"]),
            )
            col4.metric(
                "Не определено",
                len(processed_df[processed_df["Итоговый язык"] == "Unknown"]),
            )

            st.markdown("**По источникам:**")
            src_counts = processed_df["Источник"].value_counts()
            st.write(f"- Из папки синхронизации: **{src_counts.get('folder', 0)}**")
            st.write(f"- Через интерфейс: **{src_counts.get('frontend', 0)}**")
        else:
            st.warning("Нет обработанных документов для отображения статистики.")

        # ============================================================
        #  АКТИВНЫЕ ССЫЛКИ НА ДОКУМЕНТЫ
        # ============================================================
        st.subheader("Активные ссылки на документы")
        if not processed_df.empty:
            for _, row in processed_df.iterrows():
                fname = row["Имя файла"]
                fpath = os.path.join(WATCH_FOLDER, fname)
                if os.path.exists(fpath):
                    with open(fpath, "rb") as f:
                        file_bytes = f.read()
                    col_a, col_b = st.columns([4, 1])
                    with col_a:
                        st.markdown(
                            f"**{fname}** язык: **{row['Итоговый язык']}**"
                        )
                    with col_b:
                        st.download_button(
                            label="Скачать",
                            data=file_bytes,
                            file_name=fname,
                            mime="application/pdf",
                            key=f"dl_{fname}",
                        )

        # ============================================================
        #  СРЕДСТВА СОХРАНЕНИЯ И ПЕЧАТИ
        # ============================================================
        st.subheader("Сохранение и печать результатов")
        st.caption(
            "Для корректной печати используйте кнопку «Сформировать отчёт для печати» — "
            "она генерирует полноценный HTML-документ, который можно распечатать или сохранить как PDF через браузер."
        )

        col_save1, col_save2, col_save3, col_print = st.columns(4)

        with col_save1:
            csv = df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "Скачать таблицу (CSV)",
                data=csv,
                file_name="language_detection_results.csv",
                mime="text/csv",
            )

        with col_save2:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                df.to_excel(writer, sheet_name="Результаты", index=False)
                if not processed_df.empty and stats_df is not None:
                    stats_df.to_excel(writer, sheet_name="Статистика", index=False)
            st.download_button(
                "Скачать отчёт (XLSX)",
                data=buffer.getvalue(),
                file_name="language_detection_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        with col_save3:
            if not processed_df.empty:
                report_html = generate_printable_html(df, processed_df, stats_df, selected_doc)
                st.download_button(
                    " Скачать отчёт (HTML)",
                    data=report_html,
                    file_name="language_detection_report.html",
                    mime="text/html",
                )

        with col_print:
            if st.button("Сформировать отчёт для печати"):
                st.session_state['show_print_report'] = True

        # Модальное окно с отчётом для печати
        if st.session_state.get('show_print_report', False):
            if not processed_df.empty:
                report_html = generate_printable_html(df, processed_df, stats_df, selected_doc)

                st.divider()
                st.subheader("Отчёт для печати")
                st.caption(
                    "Нажмите кнопку «Распечатать отчёт» в правом верхнем углу. "
                    "В диалоге печати можно выбрать «Сохранить как PDF»."
                )

                st.components.v1.html(
                    report_html,
                    height=1400,
                    scrolling=True
                )

            if st.button("Закрыть отчёт"):
                st.session_state['show_print_report'] = False
                st.rerun()

        # ============================================================
        #  УДАЛЕНИЕ ДОКУМЕНТА
        # ============================================================
        st.subheader("Управление коллекцией")

        # Инициализация состояния удаления
        if 'delete_confirmed' not in st.session_state:
            st.session_state.delete_confirmed = False
        if 'file_to_delete' not in st.session_state:
            st.session_state.file_to_delete = None

        if not processed_df.empty:
            filenames = processed_df["Имя файла"].tolist()

            # Проверяем, есть ли ещё файлы после удаления
            if len(filenames) > 0:
                selected_file = st.selectbox(
                    "Выберите файл для удаления",
                    filenames,
                    key="delete_select",
                    help="Выберите документ, который хотите удалить из системы"
                )

                col_del1, col_del2 = st.columns([1, 3])

                with col_del1:
                    if st.button("Удалить документ", key="btn_delete", type="secondary"):
                        # Сохраняем выбранный файл в session_state
                        st.session_state.file_to_delete = selected_file
                        st.session_state.delete_confirmed = True
                        st.rerun()

                with col_del2:
                    if st.session_state.delete_confirmed and st.session_state.file_to_delete:
                        st.warning(f"Файл **{st.session_state.file_to_delete}** будет удалён безвозвратно!")

                        col_confirm1, col_confirm2 = st.columns(2)

                        with col_confirm1:
                            if st.button("Подтвердить удаление", key="btn_confirm", type="primary"):
                                try:
                                    controller.delete_document(
                                        st.session_state.file_to_delete,
                                        WATCH_FOLDER
                                    )
                                    # Очищаем состояние
                                    st.session_state.delete_confirmed = False
                                    st.session_state.file_to_delete = None
                                    st.success(f"Документ успешно удалён!")
                                    st.balloons()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Ошибка при удалении: {e}")
                                    st.session_state.delete_confirmed = False
                                    st.session_state.file_to_delete = None

                        with col_confirm2:
                            if st.button("Отмена", key="btn_cancel"):
                                st.session_state.delete_confirmed = False
                                st.session_state.file_to_delete = None
                                st.rerun()
            else:
                st.info(" Все документы удалены. Загрузите новые файлы для анализа.")
        else:
            st.info(
                "Нет документов для удаления. Загрузите файлы через интерфейс или добавьте их в папку синхронизации.")


        # Кнопка обновления
        if st.button("Обновить данные"):
            st.rerun()