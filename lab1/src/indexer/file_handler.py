import logging
import os
from io import BytesIO

import fitz
from docx import Document as DocxDocument
from striprtf.striprtf import rtf_to_text

logger = logging.getLogger(__name__)


class FileHandler:
    SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".rtf", ".docx"}

    def extract_text(self, path: str) -> str | None:
        ext = os.path.splitext(path)[1].lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return None

        try:
            with open(path, "rb") as f:
                data = f.read()
        except Exception as e:
            logger.error(f"Cannot read {path}: {e}")
            return None

        try:
            if ext == ".txt":
                return data.decode("utf-8", errors="ignore")
            if ext == ".pdf":
                doc = fitz.open(stream=data, filetype="pdf")
                try:
                    return "\n".join(page.get_text() or "" for page in doc)
                finally:
                    doc.close()
            if ext == ".docx":
                doc = DocxDocument(BytesIO(data))
                return "\n".join(p.text for p in doc.paragraphs)
            if ext == ".rtf":
                return rtf_to_text(data.decode("utf-8", errors="ignore"))
        except Exception as e:
            logger.error(f"Cannot extract text from {path}: {e}")

        return None