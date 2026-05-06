from __future__ import annotations

import logging
from typing import Any, Mapping

from .base import AgentResult, AgentStatus, AgentTask, BaseAgent

logger = logging.getLogger("jarvis.talking")


class TalkingAgent(BaseAgent):
    """Speech controller that manages voice state and delegates TTS to VoiceAgent."""

    agent_id = "talking"
    body_part = "larynx"
    capabilities = (
        "talk",
        "speaking",
        "voice_control",
        "listening_mode",
        "tts_control",
    )
    toolsets = ("voice_orchestration", "speech_control")
    hardware = ("cpu", "gpu")

    async def handle(
        self,
        task: AgentTask,
        context: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        self.status = AgentStatus.WORKING
        heart = (context or {}).get("heart")
        if heart is None:
            self.status = AgentStatus.IDLE
            return AgentResult(
                agent_id=self.agent_id,
                handled=False,
                summary="Talking controller unavailable: missing heart context.",
                data={"status": "failed", "error": "missing_heart_context"},
                confidence=0.1,
            )

        text = task.content.lower()
        state_changed = False
        status = "success"
        summary = "Talking controller is online."
        data: dict[str, Any] = {"status": status}

        if "disable voice" in text or "voice off" in text:
            heart.toggle_voice_mode(False)
            state_changed = True
            summary = "Voice listening mode disabled."
        elif "enable voice" in text or "voice on" in text:
            heart.toggle_voice_mode(True)
            heart.voice.continuous_listening = True
            state_changed = True
            summary = "Voice listening mode enabled."
        elif "disable tts" in text or "mute" in text:
            heart.toggle_tts(False)
            state_changed = True
            summary = "Voice TTS disabled."
        elif "enable tts" in text or "unmute" in text:
            heart.toggle_tts(True)
            state_changed = True
            summary = "Voice TTS enabled."

        response_text = task.metadata.get("response_text")
        if response_text and heart.voice.tts_enabled:
            try:
                mind = getattr(heart, "_mind_ref", None)
                voice_agent = mind.agents.get("voice") if mind else None
                if voice_agent:
                    await voice_agent.handle(
                        AgentTask(
                            content=str(response_text),
                            intents=["speak"],
                            metadata={
                                "speech_text": str(response_text),
                                "emotion": task.metadata.get("emotion", "calm"),
                                "intensity": task.metadata.get("intensity", 0.5),
                            },
                        ),
                        context=context,
                    )
                    summary = (
                        "Delivered spoken response via Talking controller."
                        if not state_changed
                        else f"{summary} Spoken response delivered."
                    )
                    data["spoken"] = True
                else:
                    data["spoken"] = False
                    summary = "Talking controller could not find voice agent."
                    status = "failed"
            except Exception as exc:
                logger.error("TalkingAgent speech delegation failed: %s", exc)
                status = "failed"
                summary = f"Talking controller failed to speak: {exc}"
                data["error"] = str(exc)
        else:
            data["spoken"] = False

        data["status"] = status
        data["voice_enabled"] = heart.voice.enabled
        data["tts_enabled"] = heart.voice.tts_enabled
        data["continuous_listening"] = heart.voice.continuous_listening
        self.status = AgentStatus.IDLE
        return AgentResult(
            agent_id=self.agent_id,
            handled=status == "success",
            summary=summary,
            data=data,
            confidence=0.92 if status == "success" else 0.25,
        )
