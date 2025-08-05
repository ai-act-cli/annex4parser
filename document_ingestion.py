# document_ingestion.py
from pathlib import Path
import pdfplumber

def extract_text_from_pdf(pdf_path: Path) -> str:
    """Извлекает текст из PDF-файла (не обрабатывает сканы)."""
    text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text.append(page.extract_text() or "")
    return "\n".join(text)
