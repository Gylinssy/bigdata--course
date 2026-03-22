from __future__ import annotations

import base64
import io
import os
from dataclasses import dataclass

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

try:
    import pytesseract
except ImportError:  # pragma: no cover
    pytesseract = None


class OCRBackendError(RuntimeError):
    pass


@dataclass
class OCRPageInput:
    image_bytes: bytes
    page_text_hint: str | None = None


class BaseOCRBackend:
    name = "base"

    def available(self) -> bool:
        return True

    def extract_text(self, page: OCRPageInput) -> str:
        raise NotImplementedError


class DeepSeekOCRBackend(BaseOCRBackend):
    name = "deepseek_ocr"

    def __init__(self) -> None:
        api_key = os.getenv("DEEPSEEK_API_KEY")
        base_url = os.getenv("DEEPSEEK_OCR_BASE_URL")
        self.model = os.getenv("DEEPSEEK_OCR_MODEL", "deepseek-ai/DeepSeek-OCR")
        self._client = OpenAI(api_key=api_key, base_url=base_url) if OpenAI and api_key and base_url else None

    def available(self) -> bool:
        return self._client is not None

    def extract_text(self, page: OCRPageInput) -> str:
        if not self._client:
            raise OCRBackendError("DeepSeek OCR backend is not configured.")
        image_b64 = base64.b64encode(page.image_bytes).decode("ascii")
        response = self._client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Read the page and return plain text only."},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                    ],
                }
            ],
        )
        return (response.choices[0].message.content or "").strip()


class TesseractOCRBackend(BaseOCRBackend):
    name = "tesseract"

    def available(self) -> bool:
        if Image is None or pytesseract is None:
            return False
        try:
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def extract_text(self, page: OCRPageInput) -> str:
        if not self.available():
            raise OCRBackendError("Tesseract backend is not available.")
        image = Image.open(io.BytesIO(page.image_bytes))
        return pytesseract.image_to_string(image, lang="eng+chi_sim").strip()


class PdfTextBackend(BaseOCRBackend):
    name = "pdf_text"

    def extract_text(self, page: OCRPageInput) -> str:
        return (page.page_text_hint or "").strip()


def choose_backend(preferred: str = "auto") -> BaseOCRBackend:
    backends = {
        "deepseek_ocr": DeepSeekOCRBackend(),
        "tesseract": TesseractOCRBackend(),
        "pdf_text": PdfTextBackend(),
    }
    if preferred != "auto":
        backend = backends[preferred]
        if not backend.available():
            raise OCRBackendError(f"OCR backend '{preferred}' is not available.")
        return backend

    for name in ("deepseek_ocr", "tesseract", "pdf_text"):
        backend = backends[name]
        if backend.available():
            return backend
    return PdfTextBackend()
