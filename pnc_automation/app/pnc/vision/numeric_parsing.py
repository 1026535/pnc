"""Strict numeric tokens shared by OCR row parsers."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


_INTEGER_TOKEN = r"(?:\d+|\d{1,3}(?:,\d{3})+)"
_AMOUNT_TOKEN = rf"{_INTEGER_TOKEN}(?:\.\d+)?"
INTEGER_TOKEN_PATTERN = re.compile(rf"^{_INTEGER_TOKEN}$")
AMOUNT_TOKEN_PATTERN = re.compile(rf"^{_AMOUNT_TOKEN}$")


def parse_grouped_integer(value: str) -> int | None:
    """Parse a plain or correctly comma-grouped non-negative integer."""

    token = value.strip()
    if INTEGER_TOKEN_PATTERN.fullmatch(token) is None:
        return None
    return int(token.replace(",", ""))


def parse_amount(value: str) -> Decimal | None:
    """Parse a non-negative amount with optional decimal digits and grouping."""

    token = value.strip()
    if AMOUNT_TOKEN_PATTERN.fullmatch(token) is None:
        return None
    try:
        return Decimal(token.replace(",", ""))
    except InvalidOperation:
        return None
