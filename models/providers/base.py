"""Shared model-provider contracts."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class ModelResponse(BaseModel):
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0


class ModelProvider(Protocol):
    provider: str

    def generate(self, *, model: str, input_text: str) -> ModelResponse:
        ...
