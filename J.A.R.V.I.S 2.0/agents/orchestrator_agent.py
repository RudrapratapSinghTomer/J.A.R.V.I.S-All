from __future__ import annotations

import logging
from typing import Any, Mapping

from .base import AgentResult, AgentStatus, AgentTask, BaseAgent
from core.llm_client import ModelCapability, LLMClient

logger = logging.getLogger("jarvis.orchestrator")


class OrchestratorAgent(BaseAgent):
    """The 'Nervous System Monitor' that decides which brain capability is best for a task."""

    agent_id = "orchestrator"
    body_part = "nervous_system"
    capabilities = ("model_selection", "resource_audit", "health_check")
    toolsets = ("orchestration_logic",)
    hardware = ("cpu",)

    def __init__(
        self, mcp_server: Any | None = None, llm_client: LLMClient | None = None
    ) -> None:
        super().__init__(mcp_server)
        self.llm_client = llm_client
        self.degraded_providers: set[str] = set()

    async def handle(
        self,
        task: AgentTask,
        context: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        self.status = AgentStatus.WORKING

        # 1. Resource Audit
        stats = self.audit_resources()

        # 2. Model Selection Logic (Dynamic)
        content = task.content.lower()
        required_cap = None

        # Keyword mapping (fast path)
        keyword_map = {
            ModelCapability.CODING: [
                "code",
                "script",
                "python",
                "fix",
                "error",
                "bug",
                "refactor",
            ],
            ModelCapability.HEAVY: [
                "analyze",
                "plan",
                "complex",
                "reason",
                "architecture",
                "audit",
            ],
            ModelCapability.LIGHT: [
                "hi",
                "hello",
                "how are you",
                "who are you",
                "status",
            ],
            ModelCapability.UTILITY: ["clean", "format", "json", "summarize", "route"],
            ModelCapability.VISION: [
                "see",
                "look",
                "image",
                "screenshot",
                "video",
                "camera",
                "identify",
            ],
        }

        for cap, keywords in keyword_map.items():
            if any(w in content for w in keywords):
                required_cap = cap
                break

        # LLM fallback for ambiguity (dynamic path)
        if not required_cap and self.llm_client:
            try:
                # Use LIGHT model for fast classification
                prompt = (
                    "Classify the following user request into one of these capabilities: "
                    "LIGHT, BALANCED, MEDIUM, HEAVY, UTILITY, CODING, VISION.\n"
                    f'Request: "{task.content}"\n'
                    "Output only the single word."
                )
                response = await self.llm_client.generate(
                    prompt, ModelCapability.LIGHT, purpose="orchestration"
                )
                res_word = response.text.strip().upper()
                if res_word in ModelCapability.__members__:
                    required_cap = ModelCapability[res_word]
            except Exception as e:
                logger.warning(f"Orchestrator LLM classification failed: {e}")

        required_cap = required_cap or ModelCapability.BALANCED

        # 3. Get best models and filter degraded
        final_models = []
        if self.llm_client:
            best_models = self.llm_client.select_model(
                required_cap, purpose=task.intent
            )
            healthy_models = [
                m for m in best_models if m.provider not in self.degraded_providers
            ]
            final_models = healthy_models if healthy_models else best_models

        self.status = AgentStatus.IDLE
        summary = f"Orchestration audit complete. Required Capability: {required_cap.name}. Best model: {final_models[0].id if final_models else 'None'}."

        return AgentResult(
            agent_id=self.agent_id,
            handled=True,
            summary=summary,
            data={
                "stats": stats,
                "required_cap": required_cap,
                "recommended_models": [m.id for m in final_models],
                "degraded_providers": list(self.degraded_providers),
            },
            confidence=1.0,
        )

    def audit_resources(self) -> dict[str, Any]:
        """Check system resources for real connectivity."""
        import os
        import httpx

        stats = {
            "nvidia": "Checking...",
            "ollama_local": "Checking...",
            "gemini": "Checking...",
        }

        # Simplified sync check for audit (ideally async, but this is a quick status)
        ollama_host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
        try:
            with httpx.Client(timeout=1.0) as client:
                res = client.get(f"{ollama_host}/api/tags")
                stats["ollama_local"] = (
                    "Online" if res.status_code == 200 else "Offline"
                )
        except Exception:
            stats["ollama_local"] = "Offline"

        # NVIDIA and Gemini are cloud; we assume online unless we have failures recorded
        if "nvidia" in self.degraded_providers:
            stats["nvidia"] = "Degraded"
        else:
            stats["nvidia"] = "Online"

        if "gemini" in self.degraded_providers:
            stats["gemini"] = "Degraded"
        else:
            stats["gemini"] = "Online"

        return stats

    def report_failure(self, provider: str):
        """Called when a model fails to mark it as degraded."""
        logger.warning(f"Orchestrator: Marking provider {provider} as degraded.")
        self.degraded_providers.add(provider)
