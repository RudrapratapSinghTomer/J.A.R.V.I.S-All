from __future__ import annotations

import asyncio
from typing import Any, Mapping

from .base import AgentResult, AgentStatus, AgentTask, BaseAgent


class ParallelAgent(BaseAgent):
    agent_id = "parallel"
    body_part = "muscle"
    capabilities = (
        "parallel",
        "bulk",
        "batch",
        "multi-agent",
        "massive",
        "simulation",
        "complex build",
    )
    toolsets = ("local_cores", "cloud_endpoints", "multi_agent_simulation")
    hardware = ("cpu", "cloud")

    async def handle(
        self,
        task: AgentTask,
        context: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        self.status = AgentStatus.WORKING
        subtasks = self._split_work(task.content)
        await asyncio.gather(*(self._reserve_slot(item) for item in subtasks))

        self.status = AgentStatus.IDLE
        return AgentResult(
            agent_id=self.agent_id,
            handled=True,
            summary=f"Prepared {len(subtasks)} parallel work unit(s).",
            data={"subtasks": subtasks, "execution_model": "asyncio_gather"},
            confidence=0.76,
        )

    @staticmethod
    def _split_work(content: str) -> list[str]:
        parts = [part.strip() for part in content.replace("\n", ";").split(";")]
        return [part for part in parts if part] or [content]

    @staticmethod
    async def _reserve_slot(_: str) -> None:
        await asyncio.sleep(0)
