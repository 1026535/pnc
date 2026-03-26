"""Shared text-normalization helpers used across OCR-driven runtime matching."""

from __future__ import annotations


def normalize_ocr_text(text: str) -> str:
    """Normalizes OCR text for tolerant identity and anchor matching."""

    return "".join(character for character in text.upper() if character.isalnum())
