from core.llm_router import _openai_supports_custom_temperature


def test_openai_temperature_support_detection_for_gpt5_models():
    assert _openai_supports_custom_temperature("gpt-5.5") is False
    assert _openai_supports_custom_temperature("gpt-5") is False
    assert _openai_supports_custom_temperature("o3-mini") is False
    assert _openai_supports_custom_temperature("gpt-4o-mini") is True
