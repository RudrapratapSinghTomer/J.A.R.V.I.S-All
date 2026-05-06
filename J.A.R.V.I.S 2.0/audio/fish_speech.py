from __future__ import annotations

import asyncio
import json
import os
import io
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

import sounddevice as sd

try:
    from scipy.io import wavfile
except ImportError:
    wavfile = None


@dataclass(frozen=True)
class SpeechSynthesisRequest:
    text: str
    emotion: str = "calm"
    intensity: float = 0.5
    reference_id: str | None = None
    language: str = "en"
    output_name: str = "jarvis-response"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SpeechSynthesisResult:
    ok: bool
    prepared_text: str
    endpoint: str
    audio: bytes | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class FishSpeechClient:
    """Adapter for Fish Speech / Fish Audio S2 emotional TTS."""

    EMOTION_TAGS: dict[str, tuple[str, ...]] = {
        "calm": ("[soft spoken]",),
        "serious": ("[professional broadcast tone]",),
        "happy": ("[delight]",),
        "super happy": ("[super happy]", "[delight]"),
        "excited": ("[excited]",),
        "sad": ("[sad]",),
        "whisper": ("[whisper]",),
        "laugh": ("[laugh]",),
        "angry": ("[angry]",),
        "surprised": ("[surprised]",),
        "professional": ("[professional broadcast tone]",),
    }

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        enabled: bool | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = (
            base_url or os.getenv("JARVIS_FISH_SPEECH_URL", "http://127.0.0.1:8080")
        ).rstrip("/")
        self.api_key = api_key or os.getenv("JARVIS_FISH_SPEECH_API_KEY")
        self.enabled = (
            os.getenv("JARVIS_FISH_SPEECH_ENABLED", "0") == "1"
            if enabled is None
            else enabled
        )
        self.timeout_seconds = timeout_seconds

    @property
    def tts_endpoint(self) -> str:
        return f"{self.base_url}/v1/tts"

    @property
    def health_endpoint(self) -> str:
        return f"{self.base_url}/v1/health"

    def prepare_text(
        self, text: str, emotion: str = "calm", intensity: float = 0.5
    ) -> str:
        tags = list(self.EMOTION_TAGS.get(emotion.lower(), self.EMOTION_TAGS["calm"]))
        if intensity >= 0.75 and "[emphasis]" not in tags:
            tags.append("[emphasis]")
        return f"{' '.join(tags)} {text.strip()}"

    def build_payload(self, request: SpeechSynthesisRequest) -> dict[str, Any]:
        prepared_text = self.prepare_text(
            request.text, request.emotion, request.intensity
        )
        payload: dict[str, Any] = {
            "text": prepared_text,
            "format": "wav",
            "language": request.language,
            "output": request.output_name,
        }
        if request.reference_id:
            payload["reference_id"] = request.reference_id
        if request.metadata:
            payload["metadata"] = request.metadata
        return payload

    async def synthesize(
        self, request: SpeechSynthesisRequest
    ) -> SpeechSynthesisResult:
        payload = self.build_payload(request)
        prepared_text = payload["text"]
        if not self.enabled:
            return SpeechSynthesisResult(
                ok=True,
                prepared_text=prepared_text,
                endpoint=self.tts_endpoint,
                payload=payload,
            )

        try:
            audio = await asyncio.to_thread(self._post_tts, payload)
            return SpeechSynthesisResult(
                ok=True,
                prepared_text=prepared_text,
                endpoint=self.tts_endpoint,
                audio=audio,
                payload=payload,
            )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return SpeechSynthesisResult(
                ok=False,
                prepared_text=prepared_text,
                endpoint=self.tts_endpoint,
                payload=payload,
                error=str(exc),
            )

    async def health_check(self) -> bool:
        if not self.enabled:
            return False
        try:
            return await asyncio.to_thread(self._get_health)
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _post_tts(self, payload: dict[str, Any]) -> bytes:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.tts_endpoint,
            data=body,
            headers=self._headers(),
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return response.read()

    def _get_health(self) -> bool:
        request = urllib.request.Request(
            self.health_endpoint, headers=self._headers(), method="GET"
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            data = response.read().decode("utf-8", errors="replace")
            return response.status == 200 and "ok" in data.lower()

    def play_audio(self, audio_bytes: bytes | None) -> bool:
        """Play the synthesized audio bytes directly."""
        if not audio_bytes:
            return False

        if wavfile is None:
            print("ERROR: scipy not installed. Cannot play audio.")
            return False

        try:
            # Fish Speech returns WAV bytes
            with io.BytesIO(audio_bytes) as buffer:
                samplerate, data = wavfile.read(buffer)
                sd.play(data, samplerate)
                sd.wait()  # Wait until playback is finished
            return True
        except Exception as e:
            print(f"ERROR: Failed to play audio: {e}")
            return False
