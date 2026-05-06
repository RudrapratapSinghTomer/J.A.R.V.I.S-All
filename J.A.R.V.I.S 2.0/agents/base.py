from __future__ import annotations

import abc
import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class AgentStatus(str, Enum):
    IDLE = "idle"
    WORKING = "working"
    DEGRADED = "degraded"


@dataclass(frozen=True)
class AgentTask:
    content: str
    intents: list[str] = field(default_factory=lambda: ["general"])
    metadata: Mapping[str, Any] = field(default_factory=dict)
    priority: int = 5

    @property
    def intent(self) -> str:
        """Legacy support for single intent."""
        return self.intents[0] if self.intents else "general"


@dataclass
class AgentResult:
    agent_id: str
    handled: bool
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.75


class BaseAgent(abc.ABC):
    agent_id = "base"
    body_part = "body"
    capabilities: tuple[str, ...] = ()
    toolsets: tuple[str, ...] = ()
    hardware: tuple[str, ...] = ("cpu",)

    # Shared lock for resource synchronization (e.g. terminal, git)
    shared_lock = asyncio.Lock()

    def __init__(self, mcp_server: Any | None = None) -> None:
        self.mcp_server = mcp_server
        self.status = AgentStatus.IDLE

    def can_handle(self, task: AgentTask) -> bool:
        # Priority 1: Any detected intent matches agent ID or body part
        if any(intent in {self.agent_id, self.body_part} for intent in task.intents):
            return True
        # Priority 2: Any detected intent matches a capability
        if any(intent in self.capabilities for intent in task.intents):
            return True
        # Priority 3: Content matches a capability (fallback for complex tasks)
        haystack = task.content.lower()
        return any(capability in haystack for capability in self.capabilities)

    def describe(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "body_part": self.body_part,
            "capabilities": list(self.capabilities),
            "toolsets": list(self.toolsets),
            "hardware": list(self.hardware),
            "status": self.status.value,
        }

    @abc.abstractmethod
    async def handle(
        self,
        task: AgentTask,
        context: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        """Handle a delegated task."""
