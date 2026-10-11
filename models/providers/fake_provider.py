"""Deterministic fake model provider for tests and no-key pilot mode."""

from __future__ import annotations

from models.providers.base import ModelResponse


class FakeModelProvider:
    provider = "fake"

    def generate(self, *, model: str, input_text: str) -> ModelResponse:
        words = [word for word in input_text.split() if word.strip()]
        summary = " ".join(words[:24])
        text = (
            f"[fake:{model}] План пилотного выполнения:\n"
            "1. Зафиксировать задачу и риск.\n"
            "2. Выполнить безопасный draft без внешних side effects.\n"
            "3. Записать audit/cost и вернуть результат.\n"
            f"Контекст: {summary}"
        )
        return ModelResponse(
            text=text,
            input_tokens=max(len(input_text) // 4, 1),
            output_tokens=max(len(text) // 4, 1),
            latency_ms=1,
        )
