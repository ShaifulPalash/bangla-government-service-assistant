"""Extract readable text from PDFs, falling back to OCR when needed."""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from pypdf import PdfReader

OCR_LANGUAGES = {
    "bn": "ben",
    "en": "eng",
    "mixed": "ben+eng",
}


def looks_like_usable_text(text: str, language: str = "bn") -> bool:
    """Check whether extracted text appears usable for the expected language."""
    if language not in OCR_LANGUAGES:
        raise ValueError(
            f"Unsupported language: {language!r}. Expected one of {tuple(OCR_LANGUAGES)}."
        )

    meaningful = re.sub(r"\s+", "", text)

    if len(meaningful) < 50:
        return False

    if language == "bn":
        bengali_chars = sum("\u0980" <= char <= "\u09ff" for char in meaningful)
        return bengali_chars / len(meaningful) >= 0.15

    if language == "en":
        readable_chars = sum(char.isascii() and char.isalnum() for char in meaningful)
        return readable_chars / len(meaningful) >= 0.5

    bengali_chars = sum("\u0980" <= char <= "\u09ff" for char in meaningful)
    readable_chars = sum(char.isascii() and char.isalnum() for char in meaningful)
    return (bengali_chars + readable_chars) / len(meaningful) >= 0.5


def _extract_with_ocr(
    pdf_path: Path,
    page_numbers: list[int],
    language: str = "bn",
) -> dict[int, str]:
    """OCR selected 1-based PDF page numbers using the appropriate language model."""
    if language not in OCR_LANGUAGES:
        raise ValueError(
            f"Unsupported language: {language!r}. Expected one of {tuple(OCR_LANGUAGES)}."
        )

    for executable in ("pdftoppm", "tesseract"):
        if shutil.which(executable) is None:
            raise RuntimeError(
                f"Required program '{executable}' was not found. Install Poppler and Tesseract OCR."
            )

    for model in OCR_LANGUAGES[language].split("+"):
        result = subprocess.run(
            ["tesseract", "--list-langs"],
            check=True,
            capture_output=True,
            text=True,
        )
        available = set(result.stdout.splitlines())
        if model not in available:
            raise RuntimeError(
                f"Tesseract language model '{model}' is missing. "
                f"Install the corresponding trained data for language '{language}'."
            )

    extracted_pages = {}

    with tempfile.TemporaryDirectory(prefix="bangla-gov-ocr-") as temp_dir:
        output_prefix = Path(temp_dir) / "page"

        subprocess.run(
            [
                "pdftoppm",
                "-f",
                str(min(page_numbers)),
                "-l",
                str(max(page_numbers)),
                "-png",
                "-r",
                "300",
                str(pdf_path),
                str(output_prefix),
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        image_paths = sorted(
            Path(temp_dir).glob("page-*.png"),
            key=lambda path: int(path.stem.rsplit("-", maxsplit=1)[-1]),
        )

        images_by_page = {
            int(image_path.stem.rsplit("-", maxsplit=1)[-1]): image_path
            for image_path in image_paths
        }

        for page_number in page_numbers:
            image_path = images_by_page.get(page_number)
            if image_path is None:
                raise RuntimeError(f"Rendered image for PDF page {page_number} was not found.")

            result = subprocess.run(
                [
                    "tesseract",
                    str(image_path),
                    "stdout",
                    "-l",
                    OCR_LANGUAGES[language],
                    "--psm",
                    "6",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            extracted_pages[page_number] = result.stdout.strip()

    return extracted_pages


def extract_pdf_pages(
    pdf_path: str | Path,
    language: str = "bn",
) -> list[str]:
    """Extract text page by page, using OCR only where embedded text is unusable."""
    if language not in OCR_LANGUAGES:
        raise ValueError(
            f"Unsupported language: {language!r}. Expected one of {tuple(OCR_LANGUAGES)}."
        )

    path = Path(pdf_path)

    if not path.is_file():
        raise FileNotFoundError(f"PDF file not found: {path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, received: {path.name}")

    reader = PdfReader(str(path))
    if reader.is_encrypted:
        raise ValueError(f"The PDF is encrypted and cannot be processed automatically: {path}")

    embedded_pages = [page.extract_text() or "" for page in reader.pages]

    if not embedded_pages:
        raise ValueError(f"The PDF contains no pages: {path}")

    pages_to_ocr = [
        number
        for number, text in enumerate(embedded_pages, start=1)
        if not looks_like_usable_text(text, language)
    ]

    if not pages_to_ocr:
        return embedded_pages

    ocr_pages = _extract_with_ocr(path, pages_to_ocr, language)

    return [ocr_pages.get(number, text) for number, text in enumerate(embedded_pages, start=1)]


def format_pages(pages: list[str]) -> str:
    """Join extracted pages while preserving page boundaries."""
    return "\n\n".join(
        f"--- Page {number} ---\n{text}" for number, text in enumerate(pages, start=1)
    )
