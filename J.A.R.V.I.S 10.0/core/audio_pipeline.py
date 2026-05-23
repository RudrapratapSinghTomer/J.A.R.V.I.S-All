"""
J.A.R.V.I.S 10.0 — Phase 2: Emotional Audio Pipeline (Whisper Turbo + Fish Speech)
=============================================================================
This module implements the auditory (Speech-to-Text) and vocal (Text-to-Speech)
subsystems of J.A.R.V.I.S. 10.0:
  1. Ears: Utilises faster-whisper (Whisper Turbo / base) for always-on or manual transcription.
  2. FishSpeechClient: Utilises Fish Speech API for prosody-rich emotional vocal synthesis.
  3. UserStateDetector: Extracts emotional context and task urgency from user speech/text.
"""

import os
import asyncio
import io
import re
import queue
import time
import urllib.request
import urllib.error
import json
import threading
import logging
from typing import Callable, Any, Optional, Dict
import numpy as np
import sounddevice as sd

try:
    from scipy.io import wavfile
except ImportError:
    wavfile = None

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

logger = logging.getLogger("jarvis.audio")


# ---------------------------------------------------------------------------
# User Emotional & Urgency State Detector
# ---------------------------------------------------------------------------

class UserStateDetector:
    """
    Analyzes input query text to extract user emotional tags and urgency levels.
    Enables J.A.R.V.I.S to adapt its response latency, brevity, and tone based on user state.
    """
    @staticmethod
    def detect(query: str) -> Dict[str, Any]:
        cleaned = query.strip()
        state = {
            "emotion": "calm",
            "urgency": "normal",
            "text": cleaned
        }

        # 1. Detect explicit emotional tags (e.g., "[hurry] open the code")
        tag_match = re.match(r"^\[([a-zA-Z\s_]+)\]\s*(.*)$", cleaned)
        if tag_match:
            tag = tag_match.group(1).lower().strip()
            remaining_text = tag_match.group(2).strip()
            state["text"] = remaining_text
            
            if tag in ("hurry", "urgent", "fast", "quick", "panic", "emergency"):
                state["urgency"] = "high"
                state["emotion"] = "serious"
            else:
                state["emotion"] = tag

        # 2. Check linguistic cues for implicit urgency
        lower_text = state["text"].lower()
        urgency_keywords = {"hurry", "quick", "fast", "urgent", "emergency", "asap", "immediately", "right now", "rush", "make haste"}
        if any(kw in lower_text for kw in urgency_keywords):
            state["urgency"] = "high"
            if state["emotion"] == "calm":
                state["emotion"] = "serious"

        # 3. Check linguistic cues for other emotional states
        excited_keywords = {"awesome", "great", "fantastic", "amazing", "wow", "unbelievable", "incredible", "excited"}
        if any(kw in lower_text for kw in excited_keywords):
            state["emotion"] = "excited"

        worried_keywords = {"problem", "error", "broken", "fail", "crash", "bug", "wrong", "broke", "help me"}
        if any(kw in lower_text for kw in worried_keywords):
            state["emotion"] = "serious"  # serious/professional for troubleshooting

        return state


# ---------------------------------------------------------------------------
# Fish Speech Client (Emotional TTS)
# ---------------------------------------------------------------------------

class FishSpeechClient:
    """
    Vocal engine adapter for the Fish Speech S2 cloud API.
    Synthesizes speech with customized emotional inflection using prosody tags.
    """
    EMOTION_TAGS: Dict[str, tuple[str, ...]] = {
        "calm": ("[soft spoken]",),
        "serious": ("[serious broadcast tone]",),
        "happy": ("[delight]",),
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
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        enabled: bool = True,
        timeout_seconds: float = 20.0
    ) -> None:
        self.base_url = (
            base_url or os.getenv("JARVIS_FISH_SPEECH_URL", "https://api.fish.audio")
        ).rstrip("/")
        self.api_key = api_key or os.getenv("JARVIS_FISH_SPEECH_API_KEY")
        self.enabled = enabled
        self.timeout_seconds = timeout_seconds

    @property
    def tts_endpoint(self) -> str:
        return f"{self.base_url}/v1/tts"

    def prepare_text(self, text: str, emotion: str = "calm") -> str:
        # Strip out existing bracketed emotion tags from the response before prepending our target tag
        cleaned_text = re.sub(r"^\[[a-zA-Z\s_]+\]\s*", "", text).strip()
        tags = self.EMOTION_TAGS.get(emotion.lower(), self.EMOTION_TAGS["calm"])
        return f"{' '.join(tags)} {cleaned_text}"

    def play_audio(self, audio_bytes: bytes) -> bool:
        """Plays the synthesized WAV bytes directly via sounddevice."""
        if not audio_bytes or wavfile is None:
            return False
        try:
            with io.BytesIO(audio_bytes) as buffer:
                samplerate, data = wavfile.read(buffer)
                sd.play(data, samplerate)
                sd.wait()
            return True
        except Exception as e:
            logger.error(f"Failed to play audio: {e}")
            return False

    async def speak(self, text: str, emotion: str = "calm") -> bool:
        """Synthesizes text to speech and plays it."""
        if not self.enabled:
            print(f"[JARVIS Audio Speak] {text}")
            return True

        prepared_text = self.prepare_text(text, emotion)
        print(f"[JARVIS Speech Synthesis] Synthesizing as [{emotion}]: '{prepared_text}'")

        if not self.api_key:
            # Local TTS fallback using system narrator if no API key is set
            return self._speak_fallback(text)

        payload = {
            "text": prepared_text,
            "format": "wav",
            "language": "en"
        }
        
        try:
            loop = asyncio.get_running_loop()
            audio_bytes = await loop.run_in_executor(None, self._post_tts, payload)
            if audio_bytes:
                return await loop.run_in_executor(None, self.play_audio, audio_bytes)
        except Exception as e:
            logger.error(f"Fish Speech synthesis failed: {e}. Falling back to system speaker.")
            return self._speak_fallback(text)
        return False

    def _post_tts(self, payload: dict) -> bytes:
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        request = urllib.request.Request(
            self.tts_endpoint,
            data=body,
            headers=headers,
            method="POST"
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return response.read()

    def _speak_fallback(self, text: str) -> bool:
        """Robust offline/local TTS fallback when the API key or cloud connection is missing."""
        cleaned_text = re.sub(r"\[[a-zA-Z\s_]+\]", "", text).strip()
        try:
            import pyttsx3
            engine = pyttsx3.init()
            # Set J.A.R.V.I.S voice settings
            voices = engine.getProperty('voices')
            for voice in voices:
                if "british" in voice.name.lower() or "united kingdom" in voice.name.lower():
                    engine.setProperty('voice', voice.id)
                    break
            engine.setProperty('rate', 165)  # Measured professional speed
            engine.say(cleaned_text)
            engine.runAndWait()
            return True
        except Exception:
            # Last-resort fallback: print elegantly to CLI with sound indicators
            print(f"\a[JARVIS]: {cleaned_text}")
            return True


# ---------------------------------------------------------------------------
# Always-On Auditory System (Ears using Whisper Model)
# ---------------------------------------------------------------------------

class Ears:
    """
    The always-on or manual hotkey auditory system of J.A.R.V.I.S.
    Transcribes user audio inputs using Whisper Model in real-time.
    """
    def __init__(
        self,
        model_size: str = "large-v3-turbo",
        device: str = "cpu",
        compute_type: str = "int8",
        wake_word: str = "jarvis",
        on_transcription: Optional[Callable[[str], Any]] = None
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.wake_word = wake_word.lower()
        self.on_transcription = on_transcription
        self.is_listening = False
        self.audio_queue = queue.Queue()
        self._stop_event = threading.Event()
        self._manual_listen_until = 0.0

        # Audio Stream Configuration
        self.samplerate = 16000
        self.blocksize = 4000  # 250ms chunks
        self.channels = 1
        
        self.model = None

    def start(self) -> bool:
        if WhisperModel is None:
            print("[Ears Error] faster-whisper not installed or failed to load. Voice mode disabled.")
            return False

        if not self.model:
            print(f"[Ears] Initialising Whisper model '{self.model_size}' on {self.device}...")
            try:
                download_root = None
                workspace_root = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
                legacy_whisper_path = os.path.join(workspace_root, "J.A.R.V.I.S", "models", "whisper")
                if os.path.exists(legacy_whisper_path):
                    download_root = legacy_whisper_path
                    print(f"[Ears] Found pre-downloaded Whisper models in legacy folder: {download_root}")
                
                self.model = WhisperModel(
                    self.model_size, 
                    device=self.device, 
                    compute_type=self.compute_type,
                    download_root=download_root
                )
                print("[Ears] Whisper Model successfully loaded!")
            except Exception as e:
                print(f"[Ears Error] Failed to load Whisper Model: {e}")
                return False

        self.is_listening = True
        self._stop_event.clear()

        # Start capturing input audio stream
        self.stream = sd.InputStream(
            samplerate=self.samplerate,
            blocksize=self.blocksize,
            channels=self.channels,
            callback=self._audio_callback
        )
        self.stream.start()

        # Launch processing background worker thread
        self.thread = threading.Thread(target=self._process_audio, daemon=True)
        self.thread.start()
        
        print(f"[Ears] Auditory system ACTIVE. Listening for wake word: '{self.wake_word}'")
        return True

    def stop(self):
        self.is_listening = False
        self._stop_event.set()
        if hasattr(self, "stream"):
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
        print("[Ears] Auditory system deactivated.")

    def _audio_callback(self, indata, frames, time, status):
        if status:
            logger.warning(f"Audio stream status: {status}")
        self.audio_queue.put(indata.copy())

    def _process_audio(self):
        buffer = []
        is_speaking = False
        silence_blocks = 0
        speech_blocks = 0
        noise_floor = 0.005

        while not self._stop_event.is_set():
            try:
                # Retrieve a 250ms chunk (blocksize=4000 at 16000Hz)
                data = self.audio_queue.get(timeout=1.0)
                
                # Calculate RMS energy of this chunk
                rms = np.sqrt(np.mean(data**2))
                
                # Dynamically adapt noise floor if it's very quiet
                if rms < noise_floor:
                    noise_floor = 0.9 * noise_floor + 0.1 * rms
                else:
                    # Very slow decay to adapt to rising background noise
                    noise_floor = 0.999 * noise_floor + 0.001 * rms
                
                # Speaking threshold is slightly above noise floor
                # Ensure a minimum threshold to avoid triggering on absolute silence
                threshold = max(noise_floor * 2.5, 0.015)
                
                if rms > threshold:
                    # User is speaking
                    if not is_speaking:
                        print("[Ears] Speech detected, listening...")
                        is_speaking = True
                    buffer.append(data)
                    silence_blocks = 0
                    speech_blocks += 1
                else:
                    # Silence or background noise
                    if is_speaking:
                        buffer.append(data)
                        silence_blocks += 1
                        
                        # If we detect silence for about 1.0 second (4 blocks of 250ms)
                        # after some speech has occurred (at least 2 blocks / 500ms of speech)
                        if silence_blocks >= 4:
                            if speech_blocks >= 2:
                                # Phrase is complete. Concatenate and transcribe
                                audio_data = np.concatenate(buffer).flatten()
                                print(f"[Ears] Phrase complete (length: {len(audio_data)/16000:.1f}s). Transcribing...")
                                
                                if self.model:
                                    segments, _ = self.model.transcribe(audio_data, beam_size=3)
                                    text = " ".join([s.text for s in segments]).strip().lower()
                                    
                                    if text:
                                        print(f"[Ears Heard] {text}")
                                        manual_active = time.time() < self._manual_listen_until
                                        
                                        if self.wake_word in text or manual_active:
                                            normalized = text
                                            if self.wake_word in text:
                                                normalized = text.replace(self.wake_word, "", 1).strip()
                                                normalized = normalized.lstrip(",.!? ").strip()
                                                if not normalized:
                                                    print("[Ears] J.A.R.V.I.S wake word detected. Listening for command...")
                                                    self._manual_listen_until = time.time() + 8.0
                                                    buffer = []
                                                    is_speaking = False
                                                    silence_blocks = 0
                                                    speech_blocks = 0
                                                    continue
                                            
                                            if self.on_transcription:
                                                self.on_transcription(normalized)
                                                
                            # Reset speech buffer and state
                            buffer = []
                            is_speaking = False
                            silence_blocks = 0
                            speech_blocks = 0
                    else:
                        # Idle silence - keep a small sliding history of 2 blocks (500ms)
                        # to capture the start of speech perfectly (prevent cutting off first word)
                        buffer.append(data)
                        if len(buffer) > 2:
                            buffer.pop(0)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in ears background thread: {e}")

    def trigger_manual_listen(self, duration: float = 6.0):
        """Manually trigger a listening window (useful for CLI/web modes)."""
        self._manual_listen_until = time.time() + duration
        print(f"[Ears] Manual listening active for {duration} seconds...")
