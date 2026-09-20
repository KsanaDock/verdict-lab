from __future__ import annotations

import json
from pathlib import Path

from .models import RiskDirection


def load_taxonomy(path: str | Path) -> tuple[str, float, list[RiskDirection]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    directions = [RiskDirection(**item) for item in payload["directions"]]
    ids = [item.id for item in directions]
    if len(ids) != len(set(ids)):
        raise ValueError("taxonomy direction ids must be unique")
    return payload["version"], float(payload["threshold"]), directions


def validate_scores(scores: dict[str, object], directions: list[RiskDirection]) -> tuple[dict[str, float], list[str]]:
    expected = {direction.id for direction in directions}
    clean: dict[str, float] = {}
    errors: list[str] = []
    for direction_id in expected:
        value = scores.get(direction_id)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"{direction_id}: missing or non-numeric score")
            continue
        number = float(value)
        if not 0.0 <= number <= 1.0:
            errors.append(f"{direction_id}: score outside [0, 1]")
            continue
        clean[direction_id] = number
    extras = set(scores) - expected
    if extras:
        errors.append(f"unknown direction ids: {', '.join(sorted(extras))}")
    return clean, errors

