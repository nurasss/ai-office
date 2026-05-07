"""Базовый класс агента — все 7 агентов наследуют от него."""

import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

import yaml
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool

from core.config import load_agent_config
from core.llm_router import AgentConfig, LLMRouter
from core.logger import get_logger

logger = get_logger("agents.base")

class BaseAgent(ABC):
    """Абстрактный базовый агент.

    Каждый агент имеет:
    - agent_id: уникальный строковый идентификатор
    - system_prompt: хранится в prompts/*.yaml, загружается автоматически
    - model: LLM, определённая в ModelPool
    - tools: список доступных LangChain BaseTool
    """

    AGENT_ID: str = ""
    PROMPT_FILE: str = ""

    def __init__(
        self,
        router: Optional[LLMRouter] = None,
        tools: Optional[list[BaseTool]] = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> None:
        if not self.AGENT_ID:
            raise ValueError(f"{self.__class__.__name__} must define AGENT_ID")

        self.agent_id = self.AGENT_ID
        self.router = router or LLMRouter()
        self.tools = tools or []
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.system_prompt = self._load_prompt()
        self._model: Optional[BaseChatModel] = None

        logger.info(
            "agent.initialized",
            agent_id=self.agent_id,
            tools_count=len(self.tools),
        )

    def _load_prompt(self) -> str:
        """Загрузить system_prompt из YAML-файла в prompts/."""
        if not self.PROMPT_FILE:
            return ""

        prompt_path = Path(__file__).resolve().parent.parent.parent / "prompts" / self.PROMPT_FILE
        if not prompt_path.exists():
            logger.warning("prompt.file_not_found", path=str(prompt_path))
            return ""

        with open(prompt_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return data.get("system_prompt", "")

    def get_model(self, *, use_heavy: bool = False) -> BaseChatModel:
        """Получить LLM-модель через роутер."""
        if self._model is None:
            config = AgentConfig(
                agent_id=self.agent_id,
                system_prompt=self.system_prompt,
                tools=self.tools,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            self._model = self.router.build_agent(config, use_heavy=use_heavy)
        return self._model

    @property
    def config(self) -> dict[str, Any]:
        """Загрузить конфигурацию агента из settings.yaml."""
        all_config = load_agent_config()
        return all_config.get("agents", {}).get(self.agent_id, {})

    async def invoke(
        self,
        task: str,
        context: Optional[dict[str, Any]] = None,
        *,
        use_heavy: bool = False,
    ) -> dict[str, Any]:
        """Выполнить задачу — основной метод агента.

        Args:
            task: текст задачи.
            context: дополнительный контекст от других агентов.
            use_heavy: использовать тяжёлую модель.

        Returns:
            Словарь с ключами: agent_id, task_id, result, status.
        """
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        logger.info(
            "agent.invoke.start",
            agent_id=self.agent_id,
            task_id=task_id,
            use_heavy=use_heavy,
        )

        messages: list[BaseMessage] = [
            SystemMessage(content=self.system_prompt),
        ]

        if context:
            messages.append(
                HumanMessage(content=f"Контекст от других агентов:\n{context}")
            )

        messages.append(HumanMessage(content=f"Задача:\n{task}"))

        model = self.get_model(use_heavy=use_heavy)

        try:
            response = await model.ainvoke(messages)
        except Exception as e:
            logger.error("agent.invoke.error", agent_id=self.agent_id, error=str(e))
            raise

        result = {
            "agent_id": self.agent_id,
            "task_id": task_id,
            "result": response.content,
            "status": "completed",
        }

        logger.info(
            "agent.invoke.done",
            agent_id=self.agent_id,
            task_id=task_id,
        )

        return result

    @abstractmethod
    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """Обработать состояние графа — каждая реализация своя.

        Вызывается как нода в LangGraph StateGraph.
        """
        ...
