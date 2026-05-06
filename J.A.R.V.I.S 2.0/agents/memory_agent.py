from __future__ import annotations

import asyncio
from typing import Any, Mapping

from .base import AgentResult, AgentStatus, AgentTask, BaseAgent


class MemoryAgent(BaseAgent):
    agent_id = "memory"
    body_part = "memory"
    capabilities = (
        "memory",
        "remember",
        "history",
        "reflection",
        "reflect",
        "rag",
        "life",
        "notes",
        "calendar",
    )
    toolsets = ("cognee", "contextual_rag")
    hardware = ("cpu", "cloud")

    def __init__(
        self, mcp_server: Any | None = None, memory_backend: Any | None = None
    ) -> None:
        super().__init__(mcp_server)
        if memory_backend is None:
            from core.memory.cognee_bridge import memory

            memory_backend = memory
        self.memory = memory_backend

    async def handle(
        self,
        task: AgentTask,
        context: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        print(f"DEBUG: MemoryAgent handling intent: {task.intent}")
        self.status = AgentStatus.WORKING

        content = task.content

        action = self._memory_action(task)

        if action == "remember":
            await self.memory.remember(content, metadata=task.metadata)
            summary = "I have committed that to neural memory."
            data = {"action": "remembered"}
        elif action == "recall":
            results = await self.memory.recall(content)
            if results:
                summary = f"I found {len(results)} relevant memory item(s)."
                # Format results for synthesis
                formatted_results = "\n".join(f"- {r['text']}" for r in results)
                data = {
                    "action": "recalled",
                    "results": results,
                    "result": formatted_results,
                }
            else:
                summary = "I could not find a specific memory for that."
                data = {"action": "recalled", "results": []}
        else:
            # Default to logging the interaction
            await self.memory.remember(
                f"Interaction: {content}", metadata={"type": "log"}
            )
            summary = "The interaction has been indexed."
            data = {"action": "logged"}

        self.status = AgentStatus.IDLE
        return AgentResult(
            agent_id=self.agent_id,
            handled=True,
            summary=summary,
            data=data,
            confidence=0.9,
        )

    async def reflect(self) -> AgentResult:
        self.status = AgentStatus.WORKING
        # In a real scenario, we'd pull recent events and generate an insight
        # For now, we trigger the Cognee improvement/reflection cycle
        asyncio.create_task(self.memory.improve())

        self.status = AgentStatus.IDLE
        return AgentResult(
            agent_id=self.agent_id,
            handled=True,
            summary="I am consolidating recent experiences and reflecting on our interactions.",
            data={},
            confidence=0.8,
        )

    async def initialize(self) -> bool:
        """Initialize the neural engine and load context."""
        print("DEBUG: Initializing MemoryAgent (Cognee)...")
        ok = await self.memory.initialize()
        print(f"DEBUG: MemoryAgent bridge initialized: {ok}")
        if ok:
            print("DEBUG: Loading context into memory...")
            await self.memory.load_context()
            print("DEBUG: Context loaded.")
        return ok

    @staticmethod
    def _memory_action(task: AgentTask) -> str:
        explicit = str(task.metadata.get("memory_action", "")).lower()
        if explicit in {"remember", "recall", "log"}:
            return explicit

        text = task.content.strip().lower()
        recall_markers = (
            "recall",
            "search memory",
            "what do you remember",
            "do you remember",
            "find memory",
            "tell me about your memory",
            "what is in your memory",
            "what do you have in your memory",
            "what do you know about",
        )
        remember_markers = (
            "remember",
            "save this",
            "store this",
            "commit this",
            "note this",
            "keep this in mind",
        )
        if (
            any(marker in text for marker in recall_markers)
            or text.endswith("?")
            or "memory" in text
        ):
            # If "memory" is mentioned, it's often a query unless it's a "remember" command
            if any(marker in text for marker in remember_markers):
                return "remember"
            return "recall"
        if any(marker in text for marker in remember_markers):
            return "remember"
        return "log"
