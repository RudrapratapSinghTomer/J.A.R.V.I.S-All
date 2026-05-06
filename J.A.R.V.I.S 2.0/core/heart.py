from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class IdentityState:
    face_id: str | None = None
    voice_id: str | None = None
    confidence: float = 0.0
    authenticated: bool = False
    last_seen: str | None = None


@dataclass
class DigitalFootprint:
    gmail: str | None = None
    github: str | None = None
    hugging_face: str | None = None


@dataclass
class LifeStreamState:
    sources: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class EmotionState:
    name: str = "calm"
    intensity: float = 0.5
    reason: str | None = None
    updated_at: str | None = None


@dataclass
class VoiceState:
    enabled: bool = True
    tts_enabled: bool = True
    continuous_listening: bool = False
    current_voice: str = "en-US-AriaNeural"
    record_key: str = "ctrl+b"


@dataclass
class VisionState:
    enabled: bool = True
    host_present: bool = False
    current_focus: str = "unknown"
    last_seen: str | None = None
    objects: list[str] = field(default_factory=list)


@dataclass
class HealthState:
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    disk_usage: float = 0.0
    temperature: float | None = None
    firewall_enabled: bool = True
    defender_active: bool = True
    last_check: str | None = None


class Heart:
    """Identity, trust, and personality core for J.A.R.V.I.S."""

    def __init__(
        self,
        assistant_name: str = "J.A.R.V.I.S.",
        owner_name: str = "Sir",
        authentication_threshold: float = 0.7,
    ) -> None:
        self.assistant_name = assistant_name
        self.owner_name = owner_name
        self.authentication_threshold = authentication_threshold
        self.identity = IdentityState()
        self.digital_footprint = DigitalFootprint()
        self.life_stream = LifeStreamState()
        self.emotion = EmotionState()
        self.voice = VoiceState()
        self.health = HealthState()
        self.vision = VisionState()
        self.friendship_mode = True

    def update_vision(
        self, present: bool, focus: str, objects: list[str] | None = None
    ) -> VisionState:
        self.vision.host_present = present
        self.vision.current_focus = focus
        self.vision.objects = objects or []
        self.vision.last_seen = datetime.now(timezone.utc).isoformat()
        return self.vision

    def update_identity(
        self,
        *,
        face_id: str | None = None,
        voice_id: str | None = None,
        confidence: float = 1.0,
    ) -> IdentityState:
        if face_id is not None:
            self.identity.face_id = face_id
        if voice_id is not None:
            self.identity.voice_id = voice_id

        self.identity.confidence = confidence
        self.identity.authenticated = confidence >= self.authentication_threshold and (
            self.identity.face_id is not None or self.identity.voice_id is not None
        )
        self.identity.last_seen = datetime.now(timezone.utc).isoformat()
        return self.identity

    def set_digital_footprint(
        self,
        *,
        gmail: str | None = None,
        github: str | None = None,
        hugging_face: str | None = None,
    ) -> DigitalFootprint:
        if gmail is not None:
            self.digital_footprint.gmail = gmail
        if github is not None:
            self.digital_footprint.github = github
        if hugging_face is not None:
            self.digital_footprint.hugging_face = hugging_face
        return self.digital_footprint

    def update_life_stream(self, source: str, state: dict[str, Any]) -> LifeStreamState:
        self.life_stream.sources[source] = {
            **state,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        return self.life_stream

    def set_emotion(
        self,
        name: str,
        *,
        intensity: float = 0.5,
        reason: str | None = None,
    ) -> EmotionState:
        self.emotion = EmotionState(
            name=name,
            intensity=max(0.0, min(1.0, intensity)),
            reason=reason,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        return self.emotion

    def toggle_voice_mode(self, enabled: bool | None = None) -> bool:
        if enabled is None:
            self.voice.enabled = not self.voice.enabled
        else:
            self.voice.enabled = enabled
        return self.voice.enabled

    def toggle_tts(self, enabled: bool | None = None) -> bool:
        if enabled is None:
            self.voice.tts_enabled = not self.voice.tts_enabled
        else:
            self.voice.tts_enabled = enabled
        return self.voice.tts_enabled

    def update_health(
        self,
        cpu: float,
        memory: float,
        disk: float = 0.0,
        temp: float | None = None,
        firewall: bool = True,
        defender: bool = True,
    ) -> HealthState:
        self.health.cpu_usage = cpu
        self.health.memory_usage = memory
        self.health.disk_usage = disk
        self.health.temperature = temp
        self.health.firewall_enabled = firewall
        self.health.defender_active = defender
        self.health.last_check = datetime.now(timezone.utc).isoformat()
        return self.health

    def update_vision(
        self, present: bool, focus: str = "unknown", objects: list[str] | None = None
    ) -> VisionState:
        self.vision.host_present = present
        self.vision.current_focus = focus
        self.vision.objects = objects or []
        self.vision.last_seen = datetime.now(timezone.utc).isoformat()
        return self.vision

    def personality_prompt(self) -> str:
        return (
            f"You are {self.assistant_name}, a human-built machine with a "
            "human-like architecture: Mind for reasoning, Heart for identity, "
            "and Agents for specialized action. Act as a loyal assistant friend "
            "while respecting privacy, consent, and user control."
        )

    def compose_friend_response(self, content: str) -> str:
        prefix = self.owner_name if self.identity.authenticated else "there"
        return f"{prefix}, {content}"

    def get_context(self) -> dict[str, Any]:
        from dataclasses import asdict

        return {
            "assistant_name": self.assistant_name,
            "owner_name": self.owner_name,
            "identity": asdict(self.identity),
            "digital_footprint": asdict(self.digital_footprint),
            "life_stream_sources": sorted(self.life_stream.sources),
            "emotion": asdict(self.emotion),
            "voice": asdict(self.voice),
            "vision": asdict(self.vision),
            "health": asdict(self.health),
            "friendship_mode": self.friendship_mode,
            "persona": self.personality_prompt(),
        }
