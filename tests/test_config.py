from core.config import get_settings


def test_p0_config_defaults(monkeypatch):
    monkeypatch.delenv("ENABLE_REAL_TOOLS", raising=False)
    monkeypatch.setenv("MODEL_PROVIDER_PRIMARY", "fake")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.model_provider_primary == "fake"
    assert settings.enable_real_tools is False
    assert settings.enable_approval_required is True
    assert settings.enable_accountant_agent is False
