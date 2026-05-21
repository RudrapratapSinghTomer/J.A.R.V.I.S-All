import os
import sys
import base64
import tempfile
import yaml
import requests
import threading
import time
import queue
import cv2
import numpy as np
from PIL import Image
import mss
import io

config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
with open(config_path, "r") as f:
    config = yaml.safe_load(f)

OLLAMA_URL = (
    config.get("models", {})
    .get("local", {})
    .get("endpoint", "http://localhost:11434/api")
)
VLM_MODEL = config.get("models", {}).get("local", {}).get("vlm", "llama3.2-vision:11b")


class WebcamStream(threading.Thread):
    """Threaded webcam reader."""

    def __init__(self):
        super().__init__(daemon=True)
        # Try DirectShow for Windows first (fix for -1072873822)
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            print("[Webcam] DirectShow failed, falling back to default MSMF...")
            self.cap = cv2.VideoCapture(0)

        if self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Minimise lag
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        else:
            print("[Webcam] CRITICAL: Could not open video source.")

        self.frame = None
        self.running = True

    def run(self):
        while self.running:
            if not self.cap.isOpened():
                time.sleep(1)
                continue
            ret, frame = self.cap.read()
            if ret:
                self.frame = frame
            else:
                # Avoid flooding logs if grab fails temporarily
                time.sleep(0.5)
            time.sleep(0.01)

    def read(self):
        return self.frame

    def stop(self):
        self.running = False
        self.cap.release()


class ScreenStream(threading.Thread):
    """Threaded screen reader using MSS."""

    def __init__(self):
        super().__init__(daemon=True)
        self.sct = mss.MSS()
        self.monitor = self.sct.monitors[1]
        self.frame = None
        self.running = True

    def run(self):
        while self.running:
            screenshot = self.sct.grab(self.monitor)
            # Convert to numpy array
            self.frame = np.array(screenshot)
            time.sleep(0.01)

    def read(self):
        return self.frame

    def stop(self):
        self.running = False


class VisionVLM:
    """
    Vision Language Model agent with Threaded Architecture.
    """

    def __init__(self):
        self.model = VLM_MODEL
        self.endpoint = f"{OLLAMA_URL}/generate"

        # Initialize background streams
        self.webcam = WebcamStream()
        self.screen = ScreenStream()

        # Start streams
        self.webcam.start()
        self.screen.start()

    def _query_vlm(self, image_bytes: bytes, prompt: str) -> str:
        """Call NVIDIA NIM (Cloud) or local VLM (Ollama)."""
        nvidia_key = os.getenv("NVIDIA_API_KEY")
        if nvidia_key:
            try:
                from openai import OpenAI

                client = OpenAI(
                    base_url="https://integrate.api.nvidia.com/v1", api_key=nvidia_key
                )
                encoded = base64.b64encode(image_bytes).decode("utf-8")
                completion = client.chat.completions.create(
                    model="meta/llama-3.2-90b-vision-instruct",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{encoded}"
                                    },
                                },
                            ],
                        }
                    ],
                    max_tokens=1024,
                )
                return completion.choices[0].message.content
            except Exception as e:
                print(f"[VLM] Cloud Vision failed: {e}")

        # Local Fallback
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        try:
            response = requests.post(
                self.endpoint,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "images": [encoded],
                    "stream": False,
                },
                timeout=120,
            )
            return response.json().get("response", "No response.")
        except Exception as e:
            return f"Vision error: {e}"

    def capture_dual_vision(
        self, prompt: str = "Describe everything in this view (Screen + Webcam PiP)."
    ) -> str:
        """Merges screen and webcam into a single frame for analysis."""
        # Wait up to 3 seconds for screen frame
        for _ in range(30):
            screen_frame = self.screen.read()
            if screen_frame is not None:
                break
            time.sleep(0.1)

        # Wait up to 2 seconds for webcam frame if it's currently None
        webcam_frame = self.webcam.read()
        if webcam_frame is None:
            for _ in range(20):
                webcam_frame = self.webcam.read()
                if webcam_frame is not None:
                    break
                time.sleep(0.1)

        if screen_frame is None:
            return "[VLM] Screen capture not ready. Ensure monitor is active."

        # Convert BGRA to RGB (MSS returns BGRA)
        img_screen = cv2.cvtColor(screen_frame, cv2.COLOR_BGRA2BGR)

        if webcam_frame is not None:
            # Resize webcam to PiP size (e.g., 1/4 of screen width)
            h_s, w_s = img_screen.shape[:2]
            w_w = w_s // 4
            h_w = int(webcam_frame.shape[0] * (w_w / webcam_frame.shape[1]))
            pip_webcam = cv2.resize(webcam_frame, (w_w, h_w))

            # Place in bottom-right corner
            img_screen[h_s - h_w - 10 : h_s - 10, w_s - w_w - 10 : w_s - 10] = (
                pip_webcam
            )

        # Encode to PNG
        _, buffer = cv2.imencode(".png", img_screen)
        return self._query_vlm(buffer.tobytes(), prompt)

    def analyze(self, source: str, prompt: str = "Describe what you see.") -> str:
        if source.lower() in ["screen", "dual", "live"]:
            return self.capture_dual_vision(prompt)
        return f"[VLM] Unsupported source: {source}"

    def stop(self):
        self.webcam.stop()
        self.screen.stop()
