from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


ProbabilitySource = Literal["native_distribution", "self_reported", "unavailable"]


@dataclass(frozen=True)
class RiskDirection:
    id: str
    name: str
    question: str
    present: str
    absent: str


@dataclass(frozen=True)
class ModerationCase:
    case_id: str
    content: str
    dataset: str
    split: str
    source_label: str | None = None
    gold: dict[str, bool] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    prompt_cache_hit_tokens: int | None = None
    prompt_cache_miss_tokens: int | None = None
    reported_cost_usd: float | None = None


@dataclass
class ModelResult:
    case_id: str
    provider: str
    model: str
    status: str
    scores: dict[str, float]
    probability_source: ProbabilitySource
    selected_directions: list[str]
    latency_ms: float
    usage: Usage
    cost_usd: float | None
    cost_source: str
    raw_response: dict[str, Any]
    errors: list[str] = field(default_factory=list)
    adapter_id: str | None = None

    def to_dict(self, include_raw: bool = True) -> dict[str, Any]:
        value = asdict(self)
        if not include_raw:
            value.pop("raw_response", None)
        return value
