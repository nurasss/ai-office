"""Cost-aware deterministic model router for the production pilot path."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from core.config import get_settings
from models.providers.base import ModelProvider, ModelResponse
from models.providers.fake_provider import FakeModelProvider
from security.pii import redact_pii


class ModelRequest(BaseModel):
    task_type: str
    risk_level: str
    agent_name: str
    input_text: str
    requires_reasoning: bool = False
    requires_coding: bool = False
    requires_finance: bool = False
    max_cost_usd: float | None = None


class ModelChoice(BaseModel):
    provider: str
    model: str
    tier: Literal["cheap", "mid", "strong"]
    reason: str


PRICE_PER_1K_TOKENS: dict[str, tuple[float, float]] = {
    "fake-cheap": (0.0, 0.0),
    "fake-mid": (0.0, 0.0),
    "fake-strong": (0.0, 0.0),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4o": (0.0025, 0.01),
    "gpt-5.4": (0.003, 0.012),
    "gpt-5.5": (0.006, 0.024),
}


def estimate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    input_price, output_price = PRICE_PER_1K_TOKENS.get(model, (0.001, 0.003))
    if provider == "fake":
        return 0.0
    return round((input_tokens / 1000 * input_price) + (output_tokens / 1000 * output_price), 6)


class PilotModelRouter:
    """Small model router used by worker tests and fake-mode execution."""

    def __init__(self, provider: ModelProvider | None = None) -> None:
        self.settings = get_settings()
        self.provider = provider or FakeModelProvider()

    def choose_model(self, request: ModelRequest) -> ModelChoice:
        risk = request.risk_level.lower().strip()
        task_type = request.task_type.lower().strip()
        if request.requires_finance or risk in {"high", "critical"}:
            return ModelChoice(
                provider=self.settings.model_provider_primary or "fake",
                model=self.settings.default_strong_model or "fake-strong",
                tier="strong",
                reason="High-risk or finance task requires strong tier.",
            )
        if request.requires_coding or request.requires_reasoning or task_type in {"pmo", "analysis", "code_review"}:
            return ModelChoice(
                provider=self.settings.model_provider_primary or "fake",
                model=self.settings.default_mid_model or "fake-mid",
                tier="mid",
                reason="Reasoning/coding task uses mid tier.",
            )
        return ModelChoice(
            provider=self.settings.model_provider_primary or "fake",
            model=self.settings.default_cheap_model or "fake-cheap",
            tier="cheap",
            reason="Routine classification, routing, FAQ or draft task.",
        )

    def generate(self, request: ModelRequest) -> tuple[ModelChoice, ModelResponse, str]:
        choice = self.choose_model(request)
        model_input = request.input_text
        if self.settings.enable_pii_redaction:
            model_input = redact_pii(model_input).redacted_text
        response = self.provider.generate(model=choice.model, input_text=model_input)
        return choice, response, model_input
