import streamlit as st

from src.bot.service import handle_audio, handle_message
from src.language import LANGUAGES
from src.ui.components import document_selector, selected_document_panel
from src.ui.navigation import PAGE_FILES, PAGE_TITLES
from src.ui.state import current_result, save_result


def submit_message(*, text: str | None = None, audio_bytes: bytes | None = None):
    document = st.session_state.selected_document
    if document is None:
        st.warning("Сначала выберите документ.")
        return
    if audio_bytes is not None:
        language = LANGUAGES[st.session_state.voice_language]
        st.session_state.voice_input_version += 1
        with st.spinner("Распознаю сообщение и выполняю команду..."):
            result = handle_audio(
                audio_bytes, language, document["id"],
                summary_weights=st.session_state.summary_weights,
            )
        user_text = result.data.get("recognized_text") or "Голосовое сообщение — речь не распознана."
        voice = True
    else:
        user_text, voice = text, False
        with st.spinner("Выполняю команду..."):
            result = handle_message(text, document["id"], summary_weights=st.session_state.summary_weights)
    record_id = save_result(result, prefill=True, expected_document=document)
    context = result.data.get("document", document)
    st.session_state.bot_history.extend([
        {"role": "user", "text": user_text, "voice": voice, "document": context},
        {"role": "assistant", "text": result.message, "success": result.success,
         "action": result.action, "page": result.page, "result_id": record_id, "document": context},
    ])
    st.rerun()


st.title("Помощник по документам")
notice = st.session_state.pop("selection_notice", None)
if notice:
    st.info(notice)
document_selector()
document = selected_document_panel(show_selection_link=False)

chat_background = "rgba(38, 39, 48, 0.5)" if st.context.theme.type == "dark" else "rgba(240, 242, 246, 0.5)"
result_button_background = "#383b45" if st.context.theme.type == "dark" else "#e2e6ee"
result_button_hover = "#464a56" if st.context.theme.type == "dark" else "#d4dbe6"
st.html(f"""
<style>
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {{
    background-color: {chat_background};
    padding-right: 1rem;
}}
[data-testid="stChatMessage"] [class*="st-key-open_result_"] button {{
    background-color: {result_button_background};
}}
[data-testid="stChatMessage"] [class*="st-key-open_result_"] button:hover {{
    background-color: {result_button_hover};
}}
</style>
""")

for message in st.session_state.bot_history:
    with st.chat_message(message["role"], width="stretch"):
        context = message.get("document")
        if context:
            st.caption(f"Документ — {context['title']}")
        if message["role"] == "user":
            if message.get("voice"):
                st.caption("Голосовое сообщение")
            st.text(message["text"])
        elif message["success"]:
            st.write(message["text"])
            record = current_result(message["action"])
            if record and record["id"] == message["result_id"] and message["page"]:
                if st.button(
                    f"Открыть {PAGE_TITLES[message['page']]}",
                    key=f"open_result_{message['result_id']}", type="secondary",
                ):
                    st.switch_page(PAGE_FILES[message["page"]])
        else:
            st.error(message["text"])

with st.bottom:
    with st.expander("Голосовое сообщение"):
        st.caption("Нажмите микрофон, произнесите команду, остановите запись и отправьте её.")
        recording = st.audio_input(
            "Запишите команду", sample_rate=16000, disabled=document is None,
            key=f"voice_recording_{st.session_state.voice_input_version}",
        )
        if st.button("Отправить голосовое сообщение", disabled=recording is None or document is None, type="primary"):
            submit_message(audio_bytes=recording.getvalue())

    prompt = st.chat_input(
        "Введите команду", disabled=document is None,
        key=f"chat_message_{st.session_state.voice_input_version}",
    )
if prompt:
    submit_message(text=prompt)
