from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Usage


def load_pricing(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _is_deepseek_peak(at: datetime, config: dict[str, Any]) -> bool:
    utc = at.astimezone(timezone.utc)
    if utc.weekday() not in config["peak_weekdays"]:
        return False
    return any(start <= utc.hour < end for start, end in config["peak_ranges"])


def deepseek_cost(usage: Usage, at: datetime, pricing: dict[str, Any]) -> tuple[float | None, str]:
    config = pricing["deepseek-flash"]
    if usage.completion_tokens is None:
        return None, "unknown"
    hit = usage.prompt_cache_hit_tokens
    miss = usage.prompt_cache_miss_tokens
    if hit is None or miss is None:
        return None, "unknown_cache_breakdown"
    band = "peak" if _is_deepseek_peak(at, config) else "off_peak"
    rates = config[band]
    denominator = pricing["per_tokens"]
    total = (
        hit * rates["input_cache_hit"]
        + miss * rates["input_cache_miss"]
        + usage.completion_tokens * rates["output"]
    ) / denominator
    return total, f"calculated:{pricing['snapshot_date']}:{band}"


def jev_cost(usage: Usage, pricing: dict[str, Any]) -> tuple[float | None, str]:
    if usage.reported_cost_usd is not None:
        return usage.reported_cost_usd, "provider_reported"
    if usage.prompt_tokens is None:
        return None, "unknown"
    rates = pricing["typesafe/jev-1.13"]
    completion = usage.completion_tokens or 0
    total = (usage.prompt_tokens * rates["input"] + completion * rates["output"]) / pricing["per_tokens"]
    return total, f"estimated:{pricing['snapshot_date']}"

