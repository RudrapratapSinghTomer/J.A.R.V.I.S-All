from __future__ import annotations

import logging
from typing import Any, Mapping

from core.llm_client import ModelCapability
from .base import AgentResult, AgentStatus, AgentTask, BaseAgent

logger = logging.getLogger("jarvis.emotion")


class EmotionAgent(BaseAgent):
    agent_id = "emotion_sensor"
    body_part = "amygdala"
    capabilities = ("sense", "analyze_mood", "detect_urgency", "empathize")
    toolsets = ("sentiment_analysis", "urgency_detection")
    hardware = ("cloud", "cpu")

    def __init__(
        self, mcp_server: Any | None = None, llm_client: Any | None = None
    ) -> None:
        super().__init__(mcp_server)
        self.llm_client = llm_client

    async def handle(
        self,
        task: AgentTask,
        context: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        self.status = AgentStatus.WORKING

        # Determine urgency and mood
        text = task.content.lower()

        # Simple heuristic + LLM fallback
        urgency = 0.5
        mood = "neutral"

        if any(
            word in text
            for word in (
                "hurry",
                "quick",
                "fast",
                "urgent",
                "now",
                "asap",
                "immediately",
            )
        ):
            urgency = 0.9
            mood = "focused"
        elif any(
            word in text
            for word in ("thanks", "great", "awesome", "good", "happy", "love")
        ):
            mood = "happy"
            urgency = 0.3
        elif any(
            word in text
            for word in ("error", "failed", "bad", "angry", "stupid", "wrong")
        ):
            mood = "frustrated"
            urgency = 0.7

        # LLM analysis for deeper context if available
        if self.llm_client:
            prompt = (
                "Analyze the user's emotion and urgency from this message.\n"
                f'Message: "{task.content}"\n\n'
                'Return a JSON object: {"mood": "string", "urgency": float (0-1), "reason": "string"}'
            )
            try:
                response = await self.llm_client.generate(
                    prompt, ModelCapability.LIGHT, purpose="emotion_analysis"
                )
                # Parse simple JSON if possible, else use heuristics
                import json
                import re

                match = re.search(r"\{.*\}", response.text, re.DOTALL)
                if match:
                    data = json.loads(match.group())
                    mood = data.get("mood", mood)
                    urgency = data.get("urgency", urgency)
            except Exception as e:
                logger.error(f"LLM Emotion Analysis failed: {e}")

        # Update heart if provided in context
        heart = (context or {}).get("heart")
        if heart:
            heart.set_emotion(
                name=mood,
                intensity=urgency,
                reason=f"Detected from: {task.content[:50]}...",
            )

        self.status = AgentStatus.IDLE
        return AgentResult(
            agent_id=self.agent_id,
            handled=True,
            summary=f"Detected {mood} mood with urgency {urgency:.1f}.",
            data={"mood": mood, "urgency": urgency},
            confidence=0.85,
        )
