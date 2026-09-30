import logging
import re
import unicodedata

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from src.config import CLEANER_ENABLED, CLEANER_MAX_INPUT_TOKENS, CLEANER_MAX_NEW_TOKENS, CLEANER_MODEL_NAME

logger = logging.getLogger(__name__)
_tokenizer = None
_model = None
_device = None


def _deterministic_clean(text: str) -> str:
    cleaned_chars = []
    for char in text:
        category = unicodedata.category(char)
        codepoint = ord(char)
        is_emoji = 0x1F000 <= codepoint <= 0x1FAFF
        if char in "\r\n\t":
            cleaned_chars.append(char)
        elif char == "�" or category in {"Cc", "Cf", "Cs", "Co", "Cn", "So"} or is_emoji:
            cleaned_chars.append(" ")
        else:
            cleaned_chars.append(char)

    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in "".join(cleaned_chars).splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _looks_dirty(original: str, cleaned: str) -> bool:
    if not cleaned:
        return False
    suspicious = sum(
        1
        for char in original
        if char not in "\r\n\t" and (char == "�" or unicodedata.category(char) in {"Cc", "Cf", "Cs", "Co", "Cn", "So"})
    )
    replacement_count = original.count("�")
    alphabetic_count = sum(char.isalpha() for char in cleaned)
    return replacement_count > 0 or suspicious > max(10, len(original) // 200) or alphabetic_count < 50


def _load_model():
    global _tokenizer, _model, _device
    if _model is None:
        _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        logger.info("Loading cleaner model %s on %s", CLEANER_MODEL_NAME, _device)
        _tokenizer = AutoTokenizer.from_pretrained(CLEANER_MODEL_NAME)
        model_kwargs = {"torch_dtype": torch.float16} if _device.type == "cuda" else {}
        _model = AutoModelForCausalLM.from_pretrained(CLEANER_MODEL_NAME, **model_kwargs).to(_device)
        _model.eval()
    return _tokenizer, _model, _device


def _clean_with_llm(text: str) -> str:
    tokenizer, model, device = _load_model()
    messages = [
        {
            "role": "system",
            "content": (
                "You clean extracted documents. Remove only emojis, stickers, "
                "encoding artifacts, and meaningless non-text symbols. Preserve "
                "all words, sentences, paragraphs, punctuation, order, and meaning. "
                "Do not summarize, explain, or add text. Return only the cleaned document."
            ),
        },
        {"role": "user", "content": text},
    ]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    encoded = tokenizer(
        prompt,
        return_tensors="pt",
        truncation=True,
        max_length=CLEANER_MAX_INPUT_TOKENS,
    ).to(device)
    with torch.inference_mode():
        generated = model.generate(
            **encoded,
            max_new_tokens=CLEANER_MAX_NEW_TOKENS,
            do_sample=False,
            num_beams=1,
            pad_token_id=tokenizer.eos_token_id,
        )
    new_tokens = generated[:, encoded["input_ids"].shape[1] :]
    return tokenizer.batch_decode(new_tokens, skip_special_tokens=True)[0].strip()


def clean_text(text: str) -> str:
    cleaned = _deterministic_clean(text)
    if not CLEANER_ENABLED or not _looks_dirty(text, cleaned):
        return cleaned

    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for paragraph in cleaned.split("\n\n"):
        if current and current_length + len(paragraph) > 12000:
            chunks.append("\n\n".join(current))
            current = []
            current_length = 0
        current.append(paragraph)
        current_length += len(paragraph) + 2
    if current:
        chunks.append("\n\n".join(current))

    try:
        cleaned_chunks = []
        for chunk in chunks:
            llm_cleaned = _clean_with_llm(chunk)
            if not llm_cleaned or len(llm_cleaned) < max(100, int(len(chunk) * 0.4)):
                logger.warning("Cleaner model returned suspiciously short output; using deterministic cleanup")
                return cleaned
            cleaned_chunks.append(_deterministic_clean(llm_cleaned))
        return "\n\n".join(cleaned_chunks)
    except Exception:
        logger.exception("Cleaner model failed; using deterministic cleanup")
    return cleaned


def release_model() -> None:
    global _tokenizer, _model, _device
    if _model is not None:
        del _model
        _model = None
        _tokenizer = None
        _device = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
