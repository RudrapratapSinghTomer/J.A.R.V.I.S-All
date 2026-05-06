from __future__ import annotations

import asyncio
import logging
from typing import Any, Mapping

from .base import AgentResult, AgentStatus, AgentTask, BaseAgent

logger = logging.getLogger("jarvis.system")


class SystemAgent(BaseAgent):
    """The 'Brainstem' of J.A.R.V.I.S. 2.0. Manages staggered initialization and homeostasis."""

    agent_id = "system_agent"
    body_part = "brainstem"
    capabilities = (
        "initialize_subsystems",
        "monitor_health",
        "check_staggered_boot",
        "orchestrate_startup",
    )
    toolsets = ("system_management", "lifecycle_control")
    hardware = ("cpu",)

    def __init__(self, mcp_server: Any | None = None) -> None:
        super().__init__(mcp_server)
        self.boot_sequence = [
            "memory",
            "semantic_router",
            "monitoring",
            "immune_system",
            "proprioception",
            "vision",
            "voice",
            "talking",
            "coding",
            "planning_agent",
            "evolution_engine",
        ]

    async def handle(
        self,
        task: AgentTask,
        context: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        self.status = AgentStatus.WORKING
        text = task.content.lower()

        if any(k in text for k in ("initialize", "boot", "startup")):
            return await self._staggered_initialization(context)
        if any(k in text for k in ("status", "health", "diagnostic", "report")):
            return self._system_status(context)

        self.status = AgentStatus.IDLE
        return AgentResult(
            agent_id=self.agent_id,
            handled=True,
            summary="System agent is online. Ask for 'system status' or 'initialize system'.",
            data={"status": "idle"},
        )

    def _system_status(self, context: Mapping[str, Any] | None) -> AgentResult:
        heart = (context or {}).get("heart")
        mind = getattr(heart, "_mind_ref", None) if heart else None
        running_loops: list[str] = []
        initialized: list[str] = []
        if mind:
            for aid, agent in mind.agents.items():
                if getattr(agent, "is_running", False):
                    running_loops.append(aid)
                if getattr(agent, "status", None) is not None:
                    initialized.append(aid)

        self.status = AgentStatus.IDLE
        return AgentResult(
            agent_id=self.agent_id,
            handled=True,
            summary="System diagnostic report compiled.",
            data={
                "status": "success",
                "autonomy_enabled": bool(getattr(mind, "autonomy_enabled", False))
                if mind
                else False,
                "running_loops": running_loops,
                "initialized_agents": initialized,
            },
            confidence=0.95,
        )

    async def _staggered_initialization(
        self, context: Mapping[str, Any] | None
    ) -> AgentResult:
        """Initialize agents one by one with delays to avoid resource contention."""
        heart = (context or {}).get("heart")
        mind = getattr(heart, "_mind_ref", None) if heart else None

        if not mind:
            return AgentResult(
                self.agent_id,
                False,
                "Mind reference missing in context.",
                {"status": "failed"},
            )

        init_results = []
        logger.info("Starting staggered boot sequence...")

        for agent_id in self.boot_sequence:
            agent = mind.agents.get(agent_id)
            if agent:
                logger.info(f"Initializing {agent_id}...")
                await mind._narrate(f"Initializing {agent_id.replace('_', ' ')}.")
                try:
                    if hasattr(agent, "initialize"):
                        success = await agent.initialize()
                        init_results.append(
                            {
                                "agent": agent_id,
                                "status": "success" if success else "failed",
                            }
                        )
                    else:
                        init_results.append(
                            {"agent": agent_id, "status": "skipped (no init method)"}
                        )
                except Exception as e:
                    logger.error(f"Failed to initialize {agent_id}: {e}")
                    init_results.append(
                        {"agent": agent_id, "status": "error", "error": str(e)}
                    )

                # Staggered delay
                await asyncio.sleep(0.5)

        self.status = AgentStatus.IDLE
        return AgentResult(
            agent_id=self.agent_id,
            handled=True,
            summary="Staggered system initialization complete.",
            data={"results": init_results, "status": "success"},
        )
