from __future__ import annotations

from typing import Any, Mapping

from audio import FishSpeechClient, SpeechSynthesisRequest

from .base import AgentResult, AgentStatus, AgentTask, BaseAgent


class VoiceAgent(BaseAgent):
    agent_id = "voice"
    body_part = "mouth"
    capabilities = (
        "voice",
        "speak",
        "speech",
        "tts",
        "audio",
        "emotion",
        "emotional",
        "fish",
    )
    toolsets = ("fish_speech", "emotional_tts", "reference_voice")
    hardware = ("gpu", "cpu", "cloud")

    def __init__(
        self,
        mcp_server: Any | None = None,
        fish_speech: FishSpeechClient | None = None,
    ) -> None:
        super().__init__(mcp_server)
        self.fish_speech = fish_speech or FishSpeechClient()

    async def handle(
        self,
        task: AgentTask,
        context: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        self.status = AgentStatus.WORKING
        context_data = context or {}
        heart_ref = context_data.get("heart")
        heart_data = context_data.get("heart_data")

        emotion_state: Any = {}
        if isinstance(heart_data, Mapping):
            emotion_state = heart_data.get("emotion", {})
        elif isinstance(heart_ref, Mapping):
            emotion_state = heart_ref.get("emotion", {})
        elif heart_ref is not None:
            emotion_state = getattr(heart_ref, "emotion", {})

        state_name = (
            emotion_state.get("name")
            if isinstance(emotion_state, dict)
            else getattr(emotion_state, "name", None)
        )
        state_intensity = (
            emotion_state.get("intensity")
            if isinstance(emotion_state, dict)
            else getattr(emotion_state, "intensity", None)
        )
        emotion = str(task.metadata.get("emotion") or state_name or "calm")
        intensity = float(task.metadata.get("intensity") or state_intensity or 0.5)

        speech = await self.fish_speech.synthesize(
            SpeechSynthesisRequest(
                text=task.metadata.get("speech_text", task.content),
                emotion=emotion,
                intensity=intensity,
                reference_id=task.metadata.get("reference_id"),
                metadata={"source": "jarvis_voice_agent"},
            )
        )

        if speech.ok and speech.audio:
            # Play the audio synchronously for now, or consider wrapping in to_thread
            self.fish_speech.play_audio(speech.audio)

        self.status = AgentStatus.IDLE
        mode = "generated" if speech.audio else "prepared"
        return AgentResult(
            agent_id=self.agent_id,
            handled=speech.ok,
            summary=f"{mode.capitalize()} emotional speech through Fish Speech using '{emotion}' style.",
            data={
                "prepared_text": speech.prepared_text,
                "endpoint": speech.endpoint,
                "has_audio": speech.audio is not None,
                "payload": speech.payload,
                "error": speech.error,
            },
            confidence=0.84 if speech.ok else 0.4,
        )
