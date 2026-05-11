"""LLM Router — фабрика моделей с принципом Model Routing.

Быстрые/дешёвые модели для рутины, тяжёлые — для сложной логики.
Каждый агент получает модель из своего пула на основе конфигурации.
"""

from enum import Enum
from typing import Any, Optional, Protocol

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from core.config import get_settings, load_agent_config

class Provider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "google"

class ModelPool:
    """Пул моделей с приоритетами: default (дешёвая), heavy (дорогая)."""

    def __init__(
        self,
        provider: Provider,
        default_model: str,
        heavy_model: Optional[str] = None,
    ) -> None:
        self.provider = provider
        self.default_model = default_model
        self.heavy_model = heavy_model or default_model


class MissingLLMCredentialsError(RuntimeError):
    """Понятная ошибка конфигурации, когда для провайдера не задан API-ключ."""

    def __init__(self, *, agent_id: str, provider: Provider, env_var: str) -> None:
        self.agent_id = agent_id
        self.provider = provider
        self.env_var = env_var
        super().__init__(
            f"Для агента '{agent_id}' нужен ключ {env_var} "
            f"для провайдера {provider.value}. Добавьте его в .env и перезапустите сервер."
        )


# ─── Конфигурация пулов по агентам ────────────────────────────────────
AGENT_MODEL_POOLS: dict[str, ModelPool] = {
    "pmo": ModelPool(
        provider=Provider.OPENAI,
        default_model="gpt-5.5",
        heavy_model="gpt-5.5",
    ),
    "data_analyst": ModelPool(
        provider=Provider.OPENAI,
        default_model="gpt-5.5",
        heavy_model="gpt-5.5",
    ),
    "developer": ModelPool(
        provider=Provider.OPENAI,
        default_model="gpt-5.5",
        heavy_model="gpt-5.5",
    ),
    "copywriter": ModelPool(
        provider=Provider.OPENAI,
        default_model="gpt-5.5",
        heavy_model="gpt-5.5",
    ),
    "support": ModelPool(
        provider=Provider.OPENAI,
        default_model="gpt-5.5",
        heavy_model="gpt-5.5",  # L2 escalation → heavy
    ),
    "strategist": ModelPool(
        provider=Provider.OPENAI,
        default_model="gpt-5.5",
        heavy_model="gpt-5.5",
    ),
    "accountant": ModelPool(
        provider=Provider.OPENAI,
        default_model="gpt-5.5",
        heavy_model="gpt-5.5",  # Аудит математики → heavy
    ),
}

class ToolProtocol(Protocol):
    """Protocol для LangChain-совместимых тулзов."""
    name: str
    description: str

    def invoke(self, *args: Any, **kwargs: Any) -> Any: ...

class AgentConfig:
    """Конфигурация агента: модель, промпт, инструменты."""

    def __init__(
        self,
        agent_id: str,
        system_prompt: str,
        tools: Optional[list[Any]] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> None:
        self.agent_id = agent_id
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.temperature = temperature
        self.max_tokens = max_tokens

class LLMRouter:
    """Фабрика LLM: создаёт нужную модель для каждого агента."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._cache: dict[str, BaseChatModel] = {}

    def _get_provider_key(self, provider: Provider) -> tuple[str, str]:
        """Вернуть API-ключ и имя переменной окружения для провайдера."""
        if provider == Provider.ANTHROPIC:
            return self._settings.anthropic_api_key.strip(), "ANTHROPIC_API_KEY"
        if provider == Provider.OPENAI:
            return self._settings.openai_api_key.strip(), "OPENAI_API_KEY"
        if provider == Provider.GOOGLE:
            return self._settings.google_api_key.strip(), "GOOGLE_API_KEY"
        raise ValueError(f"Unsupported provider: {provider}")

    def _get_agent_pool(self, agent_id: str) -> ModelPool:
        """Вернуть model pool из settings.yaml с fallback на встроенные значения."""
        agent_config = load_agent_config().get("agents", {}).get(agent_id, {})
        provider_value = agent_config.get("model_provider")
        default_model = agent_config.get("model_default")

        if provider_value and default_model:
            try:
                provider = Provider(provider_value)
            except ValueError as error:
                raise ValueError(
                    f"Unsupported model_provider for {agent_id}: {provider_value}"
                ) from error

            return ModelPool(
                provider=provider,
                default_model=default_model,
                heavy_model=agent_config.get("model_heavy"),
            )

        pool = AGENT_MODEL_POOLS.get(agent_id)
        if not pool:
            raise ValueError(f"Unknown agent_id: {agent_id}")
        return pool

    def get_model(
        self,
        agent_id: str,
        *,
        use_heavy: bool = False,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> BaseChatModel:
        """Получить LLM-модель для агента.

        Args:
            agent_id: идентификатор агента (напр. 'pmo', 'developer').
            use_heavy: если True, использовать 'тяжёлую' модель пула.
            temperature: переопределение температуры агента.
            max_tokens: переопределение лимита ответа агента.

        Returns:
            Инициализированная модель LangChain.
        """
        effective_temperature = 0.1 if temperature is None else temperature
        effective_max_tokens = 4096 if max_tokens is None else max_tokens
        cache_key = (
            f"{agent_id}:{'heavy' if use_heavy else 'default'}:"
            f"{effective_temperature}:{effective_max_tokens}"
        )
        if cache_key in self._cache:
            return self._cache[cache_key]

        pool = self._get_agent_pool(agent_id)

        if pool.provider == Provider.OPENAI:
            model_name = (
                self._settings.openai_heavy_model
                if use_heavy
                else self._settings.openai_default_model
            ).strip()
        else:
            model_name = pool.heavy_model if use_heavy else pool.default_model

        api_key, env_var = self._get_provider_key(pool.provider)
        if not api_key:
            raise MissingLLMCredentialsError(
                agent_id=agent_id,
                provider=pool.provider,
                env_var=env_var,
            )

        model: BaseChatModel
        if pool.provider == Provider.ANTHROPIC:
            from langchain_anthropic import ChatAnthropic

            model = ChatAnthropic(
                model=model_name,
                api_key=api_key,
                temperature=effective_temperature,
                max_tokens=effective_max_tokens,
            )
        elif pool.provider == Provider.OPENAI:
            model = ChatOpenAI(
                model=model_name,
                api_key=api_key,
                temperature=effective_temperature,
                max_tokens=effective_max_tokens,
                max_retries=1,
            )
        elif pool.provider == Provider.GOOGLE:
            from langchain_google_genai import ChatGoogleGenerativeAI

            model = ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=api_key,
                temperature=effective_temperature,
                max_output_tokens=effective_max_tokens,
            )
        else:
            raise ValueError(f"Unsupported provider: {pool.provider}")

        self._cache[cache_key] = model
        return model

    def build_agent(self, config: AgentConfig, *, use_heavy: bool = False) -> BaseChatModel:
        """Привязать tools + system_prompt к модели.

        Возвращает модель, готовую к вызову через langchain.

        Args:
            config: конфир-->игурация агента.
            use_heavy: использовать тяжёлую модель.

        Returns:
            Модель с привязанными инструментами (model.bind_tools).
        """
        model = self.get_model(
            config.agent_id,
            use_heavy=use_heavy,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )

        if config.tools:
            model = model.bind_tools(config.tools)

        return model

def get_llm(
    *,
    agent_id: str = "copywriter",
    use_heavy: bool = False,
    temperature: float = 0.5,
    max_tokens: int = 4096,
) -> BaseChatModel:
    """Вернуть реальную LLM для ad-hoc live-прогонов.

    Основной production-путь остается через LLMRouter.build_agent().
    Эта функция нужна для простых скриптов и ручных проверок.
    """
    return LLMRouter().get_model(
        agent_id,
        use_heavy=use_heavy,
        temperature=temperature,
        max_tokens=max_tokens,
    )
