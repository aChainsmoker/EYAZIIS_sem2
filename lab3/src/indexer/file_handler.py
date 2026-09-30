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
            data = open(path, "rb").read()
            if ext == ".txt":
                return data.decode("utf-8", errors="ignore")
            if ext == ".pdf":
                document = fitz.open(stream=data, filetype="pdf")
                try:
                    return "\n".join(page.get_text() or "" for page in document)
                finally:
                    document.close()
            if ext == ".docx":
                document = DocxDocument(BytesIO(data))
                return "\n".join(p.text for p in document.paragraphs)
            return rtf_to_text(data.decode("utf-8", errors="ignore"))
        except Exception as exc:
            logger.exception("Cannot extract text from %s: %s", path, exc)
            return None
