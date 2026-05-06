from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Mapping

from .base import AgentResult, AgentStatus, AgentTask, BaseAgent

logger = logging.getLogger("jarvis.security")


class SecurityAgent(BaseAgent):
    agent_id = "immune_system"
    body_part = "white_blood_cells"
    capabilities = ("verify_identity", "authorize", "audit_security", "detect_spoofing")
    toolsets = ("voice_biometrics", "liveness_detection", "access_control")
    hardware = ("gpu", "cpu")

    def __init__(self, mcp_server: Any | None = None) -> None:
        super().__init__(mcp_server)
        self.authenticator = None
        self.face_authenticator = None
        self.host_verified = False
        self.security_mode = "strict"  # strict, advisory, off

    async def initialize(self) -> bool:
        """Initialize voice and face authenticators."""
        try:
            from core.security.voice_authenticator import VoiceAuthenticator
            from core.security.face_authenticator import FaceAuthenticator

            self.authenticator = VoiceAuthenticator()
            self.face_authenticator = FaceAuthenticator()
            logger.info("Security authenticators (Voice & Face) initialized.")
            return True
        except Exception as e:
            logger.error(f"SecurityAgent initialization failed: {e}")
            return True  # Don't block startup

    async def handle(
        self,
        task: AgentTask,
        context: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        self.status = AgentStatus.WORKING
        summary = "Checking security status..."
        data = {
            "verified": False,
            "voice_ok": False,
            "face_ok": False,
            "face_enrolled": self.face_authenticator.is_enrolled
            if self.face_authenticator
            else False,
            "mode": self.security_mode,
        }

        # 0. Handle Enrollment Intent
        if "enroll" in task.intents:
            if not self.face_authenticator:
                return AgentResult(
                    self.agent_id, False, "Face authenticator not initialized.", data
                )

            success, reason = await asyncio.to_thread(
                self.face_authenticator.enroll_host
            )
            if success:
                data["face_enrolled"] = True
                return AgentResult(
                    self.agent_id,
                    True,
                    "Host face successfully enrolled and signature saved.",
                    data,
                )
            else:
                return AgentResult(
                    self.agent_id, False, f"Enrollment failed: {reason}", data
                )

        # 1. Voice Check
        audio_path = task.metadata.get("audio_path")
        voice_ok = False
        if audio_path and self.authenticator:
            voice_ok = self.authenticator.verify(audio_path)
            data["voice_ok"] = voice_ok
            if voice_ok:
                summary = "Identity verified via neural voice biometric."

        # 2. Camera Fallback (User Request: "if failed to check voice")
        face_ok = False
        if not voice_ok and self.face_authenticator:
            logger.info("Triggering camera security check...")
            face_ok, reason = await asyncio.to_thread(
                self.face_authenticator.capture_and_verify
            )
            data["face_ok"] = face_ok

            if face_ok:
                summary = "Identity verified via real-time camera check."
            elif reason == "no_face_print":
                summary = "Biometric Alert: No face print found. Face recognition is impossible until you enroll."
            else:
                summary = f"Security Alert: Camera verification failed ({reason})."

        self.host_verified = voice_ok or face_ok
        data["verified"] = self.host_verified

        # 3. Terminal/Metadata Fallback (Only if biometric check wasn't the PRIMARY goal)
        if not self.host_verified:
            source = task.metadata.get("source", "unknown")
            if source == "terminal":
                # Still verified for session, but we must report that BIOMETRICS failed
                self.host_verified = True
                data["verified"] = True
                if (
                    "face_recognition" in task.content.lower()
                    or "identify" in task.content.lower()
                ):
                    summary = f"Identity accepted via terminal session, but BIOMETRIC CHECK FAILED: {summary}"
                else:
                    summary = f"Identity verified via terminal session fallback."

        self.status = AgentStatus.IDLE
        return AgentResult(
            agent_id=self.agent_id,
            handled=True,
            summary=summary,
            data=data,
            confidence=0.98 if (voice_ok or face_ok) else 0.5,
        )

    def is_authorized(self, agent_id: str) -> bool:
        """Check if an agent is authorized to run based on current security state."""
        if self.security_mode == "off":
            return True

        high_privilege = {"coding", "hermes", "evolution_engine"}
        if agent_id in high_privilege and not self.host_verified:
            return False
        return True
