from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .base import AgentResult, AgentStatus, AgentTask, BaseAgent

logger = logging.getLogger("jarvis.thinking")


from core.llm_client import ModelCapability, require_capability


class ThinkingAgent(BaseAgent):
    agent_id = "thinking"
    body_part = "brainstem"
    capabilities = ("think", "reflect", "research", "background", "analyze")
    toolsets = ("memory_access", "journal_access", "llm_reasoning")
    hardware = ("cloud", "cpu")

    def __init__(
        self,
        mcp_server: Any | None = None,
        llm_client: Any | None = None,
        interval: float = 60.0,
    ) -> None:
        super().__init__(mcp_server)
        self.llm_client = llm_client
        self.interval = interval
        self.is_running = False
        self._loop_task: asyncio.Task | None = None
        self.project_root = Path.cwd()
        self.journal_path = self.project_root / "context" / "mind_journal.md"
        self.memory_path = self.project_root / "context" / "memory.md"

    async def initialize(self) -> bool:
        self.is_running = True
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._thinking_loop())
        logger.info("ThinkingAgent background loop started.")
        return True

    async def shutdown(self) -> None:
        self.is_running = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        logger.info("ThinkingAgent background loop stopped.")

    @require_capability(ModelCapability.MEDIUM)
    async def handle(
        self,
        task: AgentTask,
        context: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        """Manual trigger for a thinking cycle."""
        self.status = AgentStatus.WORKING
        insight = await self._perform_thinking_cycle()
        self.status = AgentStatus.IDLE
        return AgentResult(
            agent_id=self.agent_id,
            handled=True,
            summary="I have completed a deep thinking cycle.",
            data={"insight": insight},
            confidence=0.9,
        )

    async def _thinking_loop(self) -> None:
        while self.is_running:
            await asyncio.sleep(self.interval)
            try:
                await self._perform_thinking_cycle()
            except Exception as e:
                logger.error(f"Error in thinking cycle: {e}")

    async def _perform_thinking_cycle(self) -> str:
        logger.info("Performing autonomous thinking cycle...")

        # 1. Read context
        journal = self._read_file(self.journal_path)
        memory = self._read_file(self.memory_path)

        # 2. Formulate prompt
        prompt = (
            "You are the Thinking Submind of J.A.R.V.I.S. 2.0. Your goal is to analyze current progress and identify 'Next Steps' or 'Insights'.\n"
            f"Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            "## Recent Journal Entries\n"
            f"{journal[-2000:] if journal else 'No recent journal entries.'}\n\n"
            "## Long-Term Memory Summary\n"
            f"{memory[:1000] if memory else 'No long-term memory found.'}\n\n"
            "## Task\n"
            "Analyze the above and provide a concise 'Autonomous Thought'. "
            "If you identify a technical gap (e.g., missing documentation, a bug to fix, or a research topic), describe it as a 'Proposed Task'. "
            "Keep it short and professional."
        )

        # 3. Use LLM to think (NVIDIA NIM)
        if self.llm_client:
            response = await self.llm_client.generate(
                prompt, ModelCapability.BALANCED, purpose="thinking"
            )
            insight = response.text
        else:
            insight = "Simulation: I am thinking about optimizing the neural synchronization between Cognee and the main Mind."

        # 4. Record the thought
        self._record_thought(insight)
        return insight

    def _read_file(self, path: Path) -> str:
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return ""

    def _record_thought(self, insight: str) -> None:
        if not self.journal_path.parent.exists():
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"\n## [{timestamp}] Autonomous Thought\n**Insight:** {insight}\n"

        try:
            with open(self.journal_path, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception as e:
            logger.error(f"Failed to record thought: {e}")
