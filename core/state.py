"""Схема состояния (State) для LangGraph StateGraph."""

import operator
from enum import Enum
from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage

class AgentRole(str, Enum):
    """Роли агентов — узлы графа."""
    PMO = "pmo"
    DATA_ANALYST = "data_analyst"
    DEVELOPER = "developer"
    COPYWRITER = "copywriter"
    SUPPORT = "support"
    STRATEGIST = "strategist"
    ACCOUNTANT = "accountant"

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ESCALATED = "escalated"

class SubTask(TypedDict, total=False):
    """Подзадача, декомпозированная PMO."""
    task_id: str
    description: str
    assigned_to: AgentRole
    status: TaskStatus
    result: str
    priority: int  # 1 = highest
    depends_on: list[str]  # task_id зависимостей

class OfficeState(TypedDict):
    """Состояние всего офиса — разделяемое между всеми узлами графа.

    Ключевые поля:
        messages: история диалога (человеческие + AI сообщения)
        current_task: текущая задача для обработки
        active_agent: какой агент сейчас активен
        subtasks: декомпозированные подзадачи
        artifacts: промежуточные результаты (код, отчёты, тексты)
        context: дополнительный контекст для передачи между агентами
        error: информация об ошибке, если возникла
        iterations: сччик итераций для предотвращения infinite loops
    """
    messages: Annotated[list[BaseMessage], operator.add]
    current_task: str
    active_agent: str
    subtasks: Annotated[list[SubTask], operator.add]
    artifacts: dict[str, Any]
    context: dict[str, Any]
    error: str
    iterations: int
