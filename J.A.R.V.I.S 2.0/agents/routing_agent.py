from __future__ import annotations

import logging
from typing import Any, Mapping, List

from .base import AgentResult, AgentStatus, AgentTask, BaseAgent

logger = logging.getLogger("jarvis.routing")


from core.llm_client import ModelCapability, require_capability


class RoutingAgent(BaseAgent):
    agent_id = "semantic_router"
    body_part = "thalamus"
    capabilities = ("route", "detect_intent", "dispatch", "analyze_request")
    toolsets = ("dynamic_routing", "intent_discovery")
    hardware = ("cloud", "cpu")

    def __init__(
        self, mcp_server: Any | None = None, llm_client: Any | None = None
    ) -> None:
        super().__init__(mcp_server)
        self.llm_client = llm_client

    @require_capability(ModelCapability.UTILITY)
    async def handle(
        self,
        task: AgentTask,
        context: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        self.status = AgentStatus.WORKING

        # 1. Get Agent Map
        agents_metadata = (context or {}).get("agents_metadata", {})

        # 2. Construct Prompt for Dynamic Routing
        prompt = (
            "You are the Thalamus (Semantic Router) of J.A.R.V.I.S. 2.0. "
            "Your task is to analyze the user's request and determine which 'Body Parts' (Agents) should be activated.\n\n"
            "## Available Agents & Capabilities:\n"
        )

        for agent_id, meta in agents_metadata.items():
            prompt += f"- {agent_id}: {', '.join(meta.get('capabilities', []))}\n"

        prompt += (
            f'\n## User Request:\n"{task.content}"\n\n'
            "## Output Format (Strict JSON):\n"
            '{"intents": ["intent1", "intent2"], "selected_agents": ["agent_id1", "agent_id2"], "urgency": 0.0-1.0, "reason": "string"}'
        )

        intents = ["conversation"]
        selected = []
        urgency = 0.5

        if self.llm_client:
            try:
                response = await self.llm_client.generate(
                    prompt, ModelCapability.UTILITY, purpose="routing"
                )
                import json
                import re

                match = re.search(r"\{.*\}", response.text, re.DOTALL)
                if match:
                    data = json.loads(match.group())
                    intents = data.get("intents", intents)
                    selected = data.get("selected_agents", selected)
                    urgency = data.get("urgency", urgency)
            except Exception as e:
                logger.error(f"Dynamic Routing LLM failed: {e}")
                intents, selected, urgency = self._heuristic_route(task.content)
        else:
            intents, selected, urgency = self._heuristic_route(task.content)

        if not selected:
            fallback_intents, fallback_selected, fallback_urgency = self._heuristic_route(
                task.content
            )
            if fallback_selected:
                intents = fallback_intents
                selected = fallback_selected
                urgency = fallback_urgency

        self.status = AgentStatus.IDLE
        return AgentResult(
            agent_id=self.agent_id,
            handled=True,
            summary=f"Routed request to: {', '.join(selected) or 'Brain'}.",
            data={"intents": intents, "selected_agents": selected, "urgency": urgency},
            confidence=0.9,
        )

    @staticmethod
    def _heuristic_route(content: str) -> tuple[list[str], list[str], float]:
        text = content.lower()
        intents = ["conversation"]
        selected: list[str] = []
        urgency = 0.5

        def pick(intent: str, agent_id: str) -> None:
            nonlocal intents, selected
            if intents == ["conversation"]:
                intents = []
            if intent not in intents:
                intents.append(intent)
            if agent_id not in selected:
                selected.append(agent_id)

        if any(k in text for k in ("plan", "roadmap", "strategy")):
            pick("planning", "planning_agent")
        if any(k in text for k in ("code", "fix", "bug", "file", "github", "refactor")):
            pick("coding", "coding")
        if any(k in text for k in ("hermes", "autonomous", "background task")):
            pick("hermes", "hermes")
        if any(k in text for k in ("voice", "speak", "tts", "say this")):
            pick("voice", "voice")
        if any(k in text for k in ("vision", "camera", "screenshot", "screen")):
            pick("vision", "vision")
        if any(k in text for k in ("monitor", "cpu", "memory", "health")):
            pick("monitoring", "monitoring")
        if any(
            k in text
            for k in (
                "boot",
                "initialize",
                "startup",
                "system check",
                "diagnostic",
            )
        ):
            pick("system", "system_agent")
        if any(
            k in text
            for k in (
                "dashboard",
                "hud",
                "ui",
                "command center",
                "neural map",
            )
        ):
            pick("dashboard", "dashboard_agent")
        if any(k in text for k in ("urgent", "asap", "immediately", "right now")):
            urgency = 0.9

        return intents, selected, urgency
