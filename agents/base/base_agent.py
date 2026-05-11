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
from memory import LongTermMemoryStore, format_memory_context
from rag.knowledge_files import format_knowledge_file_context, search_knowledge_files
from rag.namespaces import get_agent_profile
from rag.retriever import Retriever

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
        self.retriever = Retriever(agent_id=self.agent_id)
        self.memory = LongTermMemoryStore()

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

    def get_model(
        self,
        *,
        use_heavy: bool = False,
        bind_tools: bool = True,
        max_tokens: Optional[int] = None,
    ) -> BaseChatModel:
        """Получить LLM-модель через роутер."""
        effective_max_tokens = self.max_tokens if max_tokens is None else max_tokens

        if not bind_tools:
            return self.router.get_model(
                self.agent_id,
                use_heavy=use_heavy,
                temperature=self.temperature,
                max_tokens=effective_max_tokens,
            )

        if self._model is None:
            config = AgentConfig(
                agent_id=self.agent_id,
                system_prompt=self.system_prompt,
                tools=self.tools,
                temperature=self.temperature,
                max_tokens=effective_max_tokens,
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
        use_tools: bool = True,
        remember: bool = True,
    ) -> dict[str, Any]:
        """Выполнить задачу — основной метод агента.

        Args:
            task: текст задачи.
            context: дополнительный контекст от других агентов.
            use_heavy: использовать тяжёлую модель.
            use_tools: привязать инструменты к модели.
            remember: записать успешное решение в long-term memory.

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

        try:
            response_content = await self.process_task(
                task,
                context=context,
                use_heavy=use_heavy,
                use_tools=use_tools,
            )
        except Exception as e:
            logger.error("agent.invoke.error", agent_id=self.agent_id, error=str(e))
            raise

        result = {
            "agent_id": self.agent_id,
            "task_id": task_id,
            "result": response_content,
            "status": "completed",
        }

        if remember:
            self._record_success_memory(
                task_id=task_id,
                task=task,
                outcome=response_content,
            )

        logger.info(
            "agent.invoke.done",
            agent_id=self.agent_id,
            task_id=task_id,
        )

        return result

    async def process_task(
        self,
        task: str,
        rag_context: str = "",
        context: Optional[dict[str, Any]] = None,
        *,
        use_heavy: bool = False,
        use_tools: bool = True,
        max_tokens: Optional[int] = None,
    ) -> str:
        """Выполнить задачу через реальную LLM с system prompt + RAG context."""
        messages: list[BaseMessage] = [
            SystemMessage(content=self.system_prompt),
        ]

        operational_context = rag_context.strip()
        if not operational_context:
            operational_context = await self._build_operational_context(task)

        if operational_context:
            messages.append(
                HumanMessage(
                    content=(
                        "Используй следующую базу знаний и память для ответа. "
                        "Если в базе нет ответа, не противоречь найденному контексту.\n\n"
                        f"БАЗА ЗНАНИЙ:\n{operational_context}"
                    )
                )
            )

        if context:
            messages.append(
                HumanMessage(content=f"Контекст от других агентов:\n{context}")
            )

        messages.append(HumanMessage(content=f"Выполни задачу:\n{task}"))

        return await self._invoke_text_model(
            messages,
            use_heavy=use_heavy,
            use_tools=use_tools,
            max_tokens=max_tokens,
        )

    async def _invoke_text_model(
        self,
        messages: list[BaseMessage],
        *,
        use_heavy: bool,
        use_tools: bool,
        max_tokens: Optional[int],
    ) -> str:
        """Invoke the chat model and retry once if a reasoning model returns empty text."""
        model = self.get_model(
            use_heavy=use_heavy,
            bind_tools=use_tools,
            max_tokens=max_tokens,
        )
        response = await model.ainvoke(messages)
        content = self._stringify_response_content(response.content).strip()
        if content:
            return content

        logger.warning(
            "agent.empty_model_response",
            agent_id=self.agent_id,
            response_metadata=getattr(response, "response_metadata", {}),
            additional_kwargs=getattr(response, "additional_kwargs", {}),
        )

        retry_max_tokens = max(max_tokens or self.max_tokens, 2400)
        retry_messages = [
            *messages,
            HumanMessage(
                content=(
                    "Предыдущий ответ модели был пустым. Верни обычный текстовый ответ. "
                    "Если в базе знаний нет нужных данных, прямо скажи, каких данных не хватает, "
                    "и не оставляй ответ пустым."
                )
            ),
        ]
        retry_model = self.get_model(
            use_heavy=use_heavy,
            bind_tools=use_tools,
            max_tokens=retry_max_tokens,
        )
        retry_response = await retry_model.ainvoke(retry_messages)
        retry_content = self._stringify_response_content(retry_response.content).strip()
        if retry_content:
            return retry_content

        logger.warning(
            "agent.empty_model_response_after_retry",
            agent_id=self.agent_id,
            response_metadata=getattr(retry_response, "response_metadata", {}),
            additional_kwargs=getattr(retry_response, "additional_kwargs", {}),
        )
        return ""

    async def _build_operational_context(self, task: str) -> str:
        """Collect isolated RAG and memory context for the current agent."""
        blocks: list[str] = []

        try:
            rag_documents = await self.retriever.retrieve(task, agent_id=self.agent_id)
        except Exception as error:
            logger.warning(
                "agent.rag_context.failed",
                agent_id=self.agent_id,
                error=str(error),
            )
            rag_documents = []

        if rag_documents:
            rag_documents = self._select_rag_documents(rag_documents)
            blocks.append(self._format_rag_context(rag_documents))

        if not self._has_agent_rag_hit(rag_documents):
            try:
                knowledge_hits = search_knowledge_files(self.agent_id, task, top_k=3)
            except Exception as error:
                logger.warning(
                    "agent.knowledge_file_context.failed",
                    agent_id=self.agent_id,
                    error=str(error),
                )
                knowledge_hits = []

            knowledge_hits = self._select_knowledge_hits(knowledge_hits)
            knowledge_context = format_knowledge_file_context(knowledge_hits)
            if knowledge_context:
                blocks.append(knowledge_context)

        try:
            memory_events = self.memory.search(agent_id=self.agent_id, query=task)
        except Exception as error:
            logger.warning(
                "agent.memory_context.failed",
                agent_id=self.agent_id,
                error=str(error),
            )
            memory_events = []

        memory_context = format_memory_context(memory_events)
        if memory_context:
            blocks.append(memory_context)

        return "\n\n".join(blocks)

    def _record_success_memory(
        self,
        *,
        task_id: str,
        task: str,
        outcome: str,
    ) -> None:
        """Persist a compact successful outcome without blocking the response."""
        memory_config = load_agent_config().get("memory", {})
        if not memory_config.get("record_successes", True):
            return

        try:
            self.memory.record_success(
                agent_id=self.agent_id,
                task=task,
                outcome=outcome,
                metadata={"task_id": task_id},
            )
        except Exception as error:
            logger.warning(
                "agent.memory_record.failed",
                agent_id=self.agent_id,
                task_id=task_id,
                error=str(error),
            )

    @staticmethod
    def _format_rag_context(documents: list[dict[str, Any]]) -> str:
        """Render RAG documents into a compact prompt block."""
        lines = ["Контекст из изолированной базы знаний агента:"]
        for index, document in enumerate(documents, start=1):
            metadata = document.get("metadata", {})
            source = metadata.get("source") or metadata.get("source_id") or "unknown"
            content = str(document.get("content", "")).strip()
            source_content = BaseAgent._read_full_knowledge_source(str(source))
            if source_content:
                content = source_content
            if len(content) > 6000:
                content = f"{content[:6000]}..."
            lines.append(f"[{index}] source={source}\n{content}")
        return "\n".join(lines)

    @staticmethod
    def _stringify_response_content(content: Any) -> str:
        """Normalize provider-specific message content into plain text."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if text:
                        parts.append(str(text))
            return "\n".join(parts)
        return str(content or "")

    @staticmethod
    def _read_full_knowledge_source(source: str) -> str:
        """Read a full committed knowledge file when RAG points at one."""
        if not source.startswith("knowledge/"):
            return ""

        source_path = Path(__file__).resolve().parent.parent.parent / source
        if not source_path.exists() or not source_path.is_file():
            return ""

        try:
            return source_path.read_text(encoding="utf-8").strip()
        except UnicodeDecodeError:
            return source_path.read_text(encoding="utf-8", errors="ignore").strip()

    def _has_agent_rag_hit(self, documents: list[dict[str, Any]]) -> bool:
        """Return True when RAG already found agent-specific knowledge."""
        if not documents:
            return False

        agent_namespace = get_agent_profile(self.agent_id)["namespace"]
        for document in documents:
            metadata = document.get("metadata", {})
            if (
                metadata.get("agent_id") == self.agent_id
                or metadata.get("namespace") == agent_namespace
            ):
                return True
        return False

    def _select_rag_documents(self, documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Prefer agent-owned RAG hits and remove duplicate sources."""
        agent_namespace = get_agent_profile(self.agent_id)["namespace"]
        agent_documents = [
            document
            for document in documents
            if document.get("metadata", {}).get("agent_id") == self.agent_id
            or document.get("metadata", {}).get("namespace") == agent_namespace
        ]
        selected = agent_documents or documents

        unique_documents: list[dict[str, Any]] = []
        seen_sources: set[str] = set()
        for document in selected:
            metadata = document.get("metadata", {})
            source = str(metadata.get("source") or metadata.get("source_id") or "")
            if source and source in seen_sources:
                continue
            if source:
                seen_sources.add(source)
            unique_documents.append(document)
        return unique_documents[:2]

    def _select_knowledge_hits(self, hits: list[Any]) -> list[Any]:
        """Prefer agent-owned file hits when committed knowledge is used."""
        agent_hits = [hit for hit in hits if getattr(hit, "agent_id", "") == self.agent_id]
        return (agent_hits or hits)[:2]

    @abstractmethod
    async def process(self, state: dict[str, Any]) -> dict[str, Any]:
        """Обработать состояние графа — каждая реализация своя.

        Вызывается как нода в LangGraph StateGraph.
        """
        ...
