from __future__ import annotations

import re
from typing import Any


NUMBER_TOKEN_RE = re.compile(
    r"(?P<value>-?\d+(?:,\d{3})*(?:\.\d+)?)\s*(?P<unit>万亿|亿|万|千|百|trillion|billion|million|k|m|b)?",
    re.IGNORECASE,
)

UNIT_MULTIPLIERS = {
    "": 1.0,
    "百": 100.0,
    "千": 1_000.0,
    "万": 10_000.0,
    "亿": 100_000_000.0,
    "万亿": 1_000_000_000_000.0,
    "k": 1_000.0,
    "m": 1_000_000.0,
    "b": 1_000_000_000.0,
    "million": 1_000_000.0,
    "billion": 1_000_000_000.0,
    "trillion": 1_000_000_000_000.0,
}


def coerce_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None

    text = value.strip().replace("，", ",")
    matches = list(NUMBER_TOKEN_RE.finditer(text))
    if not matches:
        return None

    match = matches[-1]
    number = float(match.group("value").replace(",", ""))
    unit = (match.group("unit") or "").lower()
    return number * UNIT_MULTIPLIERS.get(unit, 1.0)
