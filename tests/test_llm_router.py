from core.llm_router import (
    LLMRouter,
    Provider,
    _openai_supports_custom_temperature,
    _openai_temperature_for_model,
)


def test_openai_temperature_support_detection_for_gpt5_models():
    assert _openai_supports_custom_temperature("gpt-5.5") is False
    assert _openai_supports_custom_temperature("gpt-5") is False
    assert _openai_supports_custom_temperature("o3-mini") is False
    assert _openai_supports_custom_temperature("gpt-4o-mini") is True


def test_openai_temperature_is_default_for_fixed_temperature_models():
    assert _openai_temperature_for_model("gpt-5.4", 0.7) == 1.0
    assert _openai_temperature_for_model("o4-mini", 0.2) == 1.0
    assert _openai_temperature_for_model("gpt-4o-mini", 0.3) == 0.3


def test_fake_provider_does_not_require_api_key(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER_PRIMARY", "fake")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    router = LLMRouter()
    pool = router._get_agent_pool("data_analyst")
    model = router.get_model("data_analyst")

    assert pool.provider == Provider.FAKE
    assert model._llm_type == "ai-office-fake"
