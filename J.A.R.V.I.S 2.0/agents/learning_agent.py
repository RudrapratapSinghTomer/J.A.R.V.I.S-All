from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .base import AgentResult, AgentStatus, AgentTask, BaseAgent
from core.llm_client import ModelCapability, require_capability

logger = logging.getLogger("jarvis.learning")


class LearningAgent(BaseAgent):
    agent_id = "learning_center"
    body_part = "neurons"
    capabilities = ("learn", "evolve", "update", "research", "improve")
    toolsets = ("self_modification", "memory_synthesis", "skill_acquisition")
    hardware = ("cloud", "cpu")

    def __init__(
        self,
        mcp_server: Any | None = None,
        llm_client: Any | None = None,
        interval: float = 300.0,  # Learn every 5 minutes
    ) -> None:
        super().__init__(mcp_server)
        self.llm_client = llm_client
        self.interval = interval
        self.is_running = False
        self._loop_task: asyncio.Task | None = None
        self.project_root = Path.cwd()
        self.journal_path = self.project_root / "context" / "mind_journal.md"

    async def initialize(self) -> bool:
        self.is_running = True
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._learning_loop())
        logger.info("LearningAgent background loop started.")
        return True

    async def shutdown(self) -> None:
        self.is_running = False
        if self._loop_task:
            self._loop_task.cancel()
        logger.info("LearningAgent background loop stopped.")

    async def handle(
        self, task: AgentTask, context: Mapping[str, Any] | None = None
    ) -> AgentResult:
        self.status = AgentStatus.WORKING
        plan_data = await self._perform_learning_cycle()
        self.status = AgentStatus.IDLE
        return AgentResult(
            agent_id=self.agent_id,
            handled=True,
            summary=f"Skill acquisition cycle completed. Proposed: {plan_data.get('feature', 'Unknown')}",
            data={"evolution_plan": plan_data},
            confidence=0.95,
        )

    async def _learning_loop(self) -> None:
        while self.is_running:
            await asyncio.sleep(self.interval)
            try:
                await self._perform_learning_cycle()
            except Exception as e:
                logger.error(f"Error in learning cycle: {e}")

    async def _perform_learning_cycle(self) -> dict[str, Any]:
        logger.info("Performing autonomous learning cycle...")

        # 1. Read Personality and History
        history_path = self.project_root / "context" / "memory.md"
        history = (
            history_path.read_text(encoding="utf-8") if history_path.exists() else ""
        )

        # 2. Formulate Learning Prompt
        prompt = (
            "You are the Learning Submind of J.A.R.V.I.S. 2.0. Your persona is: 'Assistant friend who is free to learn anything, "
            "goal is to be the best, learn something new daily, research and implement new features.'\n\n"
            "## Recent Memories\n"
            f"{history[-3000:]}\n\n"
            "## Task\n"
            "1. Identify one NEW feature or improvement for J.A.R.V.I.S. 2.0 based on recent interactions.\n"
            "2. Propose a technical plan to implement it.\n"
            '3. Return ONLY a JSON: {"feature": "name", "plan": "description", "priority": "high/med/low"}'
        )

        plan_data = {
            "feature": "Neural Refinement",
            "plan": "Optimize internal RAG thresholds.",
            "priority": "low",
        }

        if self.llm_client:
            try:
                response = await self.llm_client.generate(
                    prompt, ModelCapability.BALANCED, purpose="self_improvement"
                )
                import json
                import re

                match = re.search(r"\{.*\}", response.text, re.DOTALL)
                if match:
                    plan_data = json.loads(match.group())
            except Exception as e:
                logger.error(f"Failed to parse learning insight: {e}")

        # 3. Record in Journal
        self._record_learning(plan_data)
        return plan_data

    def _record_learning(self, plan_data: dict[str, Any]) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = (
            f"\n## [{timestamp}] Learning & Self-Improvement\n"
            f"**Feature:** {plan_data.get('feature')}\n"
            f"**Plan:** {plan_data.get('plan')}\n"
            f"**Priority:** {plan_data.get('priority')}\n"
            "**Status:** Proposed to Evolution Engine\n"
        )
        with open(self.journal_path, "a", encoding="utf-8") as f:
            f.write(entry)
        logger.info(f"Recorded new learning insight: {plan_data.get('feature')}...")
