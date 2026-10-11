from models.router import ModelRequest, PilotModelRouter, estimate_cost


def test_pilot_model_router_selects_tiers(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER_PRIMARY", "fake")

    router = PilotModelRouter()

    cheap = router.choose_model(ModelRequest(task_type="faq", risk_level="safe", agent_name="support", input_text="hi"))
    mid = router.choose_model(
        ModelRequest(task_type="code_review", risk_level="safe", agent_name="developer", input_text="review", requires_coding=True)
    )
    strong = router.choose_model(
        ModelRequest(task_type="finance", risk_level="critical", agent_name="accountant", input_text="audit", requires_finance=True)
    )

    assert cheap.tier == "cheap"
    assert mid.tier == "mid"
    assert strong.tier == "strong"


def test_estimate_cost_fake_is_zero():
    assert estimate_cost("fake", "fake-mid", 1000, 1000) == 0.0
