from __future__ import annotations

import asyncio
import logging
import queue
import sys
import threading
import time
from typing import Callable, Any

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel
import keyboard

logger = logging.getLogger("jarvis.ears")


class Ears:
    """The auditory system of J.A.R.V.I.S. (Always-on Listener)"""

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        wake_word: str = "jarvis",
        on_transcription: Callable[[str], Any] | None = None,
    ) -> None:
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)
        self.wake_word = wake_word.lower()
        self.on_transcription = on_transcription
        self.is_listening = False
        self.audio_queue = queue.Queue()
        self._stop_event = threading.Event()
        self._manual_listen_until = 0.0

        # Audio Settings
        self.samplerate = 16000
        self.blocksize = 4000  # 250ms chunks
        self.channels = 1

    def start(self):
        self.is_listening = True
        self._stop_event.clear()

        # Start Audio Stream
        self.stream = sd.InputStream(
            samplerate=self.samplerate,
            blocksize=self.blocksize,
            channels=self.channels,
            callback=self._audio_callback,
        )
        self.stream.start()

        # Start Processing Thread
        self.thread = threading.Thread(target=self._process_audio, daemon=True)
        self.thread.start()

        # Setup Hotkey
        keyboard.add_hotkey("ctrl+b", self._manual_trigger)

        logger.info(f"Auditory system ONLINE. Wake word: '{self.wake_word}'")

    def stop(self):
        self.is_listening = False
        self._stop_event.set()
        if hasattr(self, "stream"):
            self.stream.stop()
            self.stream.close()
        logger.info("Auditory system OFFLINE.")

    def _audio_callback(self, indata, frames, time, status):
        if status:
            logger.warning(f"Audio status: {status}")
        self.audio_queue.put(indata.copy())

    def _process_audio(self):
        buffer = []
        while not self._stop_event.is_set():
            try:
                data = self.audio_queue.get(timeout=1.0)
                buffer.append(data)

                # Process every 2 seconds (8 blocks)
                if len(buffer) >= 8:
                    audio_data = np.concatenate(buffer).flatten()
                    buffer = []  # Reset buffer

                    # Transcribe
                    segments, _ = self.model.transcribe(audio_data, beam_size=5)
                    text = " ".join([s.text for s in segments]).strip().lower()

                    if text:
                        logger.info(f"Heard: {text}")
                        manual_window_active = time.time() < self._manual_listen_until
                        if self.wake_word in text or manual_window_active:
                            normalized = text
                            if self.wake_word in text:
                                normalized = text.replace(self.wake_word, "", 1).strip()
                                normalized = normalized.lstrip(",.!? ").strip()
                                if not normalized:
                                    # Wake word only; wait for the next phrase.
                                    self._manual_listen_until = time.time() + 6.0
                                    continue
                            if self.on_transcription:
                                self.on_transcription(normalized)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in auditory processing: {e}")

    def _manual_trigger(self):
        logger.info("Manual voice trigger detected (Ctrl+B).")
        self._manual_listen_until = time.time() + 6.0
