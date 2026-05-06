from __future__ import annotations

import asyncio
import logging
from typing import Any, Mapping

from .base import AgentResult, AgentStatus, AgentTask, BaseAgent

logger = logging.getLogger("jarvis.evolution")


class SelfUpdateAgent(BaseAgent):
    agent_id = "evolution_engine"
    body_part = "neural_plasticity"
    capabilities = ("self_update", "apply_improvements", "evolve", "repair")
    toolsets = ("code_modification", "system_reloading")
    hardware = ("cpu", "cloud")

    def __init__(
        self, mcp_server: Any | None = None, coding_agent: BaseAgent | None = None
    ) -> None:
        super().__init__(mcp_server)
        self.coding_agent = coding_agent

    async def handle(
        self,
        task: AgentTask,
        context: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        self.status = AgentStatus.WORKING

        plan = task.metadata.get("plan")
        if not plan:
            return AgentResult(
                agent_id=self.agent_id,
                handled=False,
                summary="No evolution plan provided.",
                confidence=0.0,
            )

        logger.info(
            f"Initiating autonomous evolution: {plan.get('feature', 'Unknown')}"
        )

        # 1. Prepare Coding Task
        coding_task = AgentTask(
            content=f"Implement this improvement plan: {plan.get('plan')}",
            intents=["coding"],
            metadata={"priority": "high", "autonomous": True},
        )

        if self.coding_agent:
            # 2. Execute Update
            result = await self.coding_agent.handle(coding_task, context=context)

            if result.handled:
                # 3. Verify System (Simple check for now)
                # In a real setup, we'd run pytest here.
                summary = f"Autonomous update successful: {plan.get('feature')}. System has evolved."
                logger.info(summary)

                self.status = AgentStatus.IDLE
                return AgentResult(
                    agent_id=self.agent_id,
                    handled=True,
                    summary=summary,
                    data={"evolution_result": result.data},
                    confidence=0.98,
                )
            else:
                self.status = AgentStatus.IDLE
                return AgentResult(
                    agent_id=self.agent_id,
                    handled=False,
                    summary=f"Evolution failed: {result.summary}",
                    data={"error": result.data},
                    confidence=0.1,
                )

        self.status = AgentStatus.IDLE
        return AgentResult(
            agent_id=self.agent_id,
            handled=False,
            summary="CodingAgent not available for evolution.",
            confidence=0.0,
        )
