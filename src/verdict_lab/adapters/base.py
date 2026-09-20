from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import ModelResult, ModerationCase, RiskDirection


class ModerationAdapter(ABC):
    @abstractmethod
    def evaluate(self, case: ModerationCase, directions: list[RiskDirection], threshold: float) -> ModelResult:
        raise NotImplementedError

