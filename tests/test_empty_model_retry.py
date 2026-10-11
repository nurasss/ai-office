from langchain_core.messages import AIMessage

from agents.base.base_agent import BaseAgent


class FakeModel:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0

    async def ainvoke(self, messages):
        response = self.responses[self.calls]
        self.calls += 1
        return response


class RetryAgent(BaseAgent):
    AGENT_ID = "copywriter"
    PROMPT_FILE = ""

    def __init__(self, fake_model):
        self.fake_model = fake_model
        self.max_token_requests = []
        super().__init__()

    def get_model(self, **kwargs):
        self.max_token_requests.append(kwargs.get("max_tokens"))
        return self.fake_model

    async def _build_operational_context(self, task: str) -> str:
        return ""

    async def process(self, state):
        return state


def test_process_task_retries_empty_model_response():
    model = FakeModel([
        AIMessage(content=""),
        AIMessage(content="Теперь ответ не пустой."),
    ])
    agent = RetryAgent(model)

    import asyncio

    result = asyncio.run(agent.process_task("тест", use_tools=False, max_tokens=1200))

    assert result == "Теперь ответ не пустой."
    assert model.calls == 2


def test_empty_retry_uses_agent_configured_token_limit():
    model = FakeModel([
        AIMessage(content=""),
        AIMessage(content="После увеличенного лимита есть текст."),
    ])
    agent = RetryAgent(model)
    agent.max_tokens = 8192

    import asyncio

    result = asyncio.run(agent.process_task("тест", use_tools=False, max_tokens=2400))

    assert result == "После увеличенного лимита есть текст."
    assert agent.max_token_requests == [2400, 8192]


def test_process_task_returns_fallback_after_two_empty_responses():
    model = FakeModel([
        AIMessage(content=""),
        AIMessage(content=""),
    ])
    agent = RetryAgent(model)

    import asyncio

    result = asyncio.run(agent.process_task("важная задача", use_tools=False, max_tokens=1200))

    assert "локальный fallback" in result
    assert "важная задача" in result
    assert model.calls == 2


def test_stringify_response_content_extracts_text_blocks():
    content = [
        {"type": "text", "text": "Первый блок"},
        {"type": "output_text", "content": "Второй блок"},
    ]

    assert BaseAgent._stringify_response_content(content) == "Первый блок\nВторой блок"
