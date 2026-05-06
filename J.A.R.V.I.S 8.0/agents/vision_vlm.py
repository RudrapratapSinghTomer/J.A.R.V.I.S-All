import os
import sys
import base64
import tempfile
import yaml
import requests

config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
with open(config_path, "r") as f:
    config = yaml.safe_load(f)

OLLAMA_URL = (
    config.get("models", {})
    .get("local", {})
    .get("endpoint", "http://localhost:11434/api")
)
VLM_MODEL = config.get("models", {}).get("local", {}).get("vlm", "llama3.2-vision:11b")


class VisionVLM:
    """
    Vision Language Model agent.

    Capabilities:
    1. process_image(path, prompt)  — analyze a local image file
    2. capture_screen(prompt)       — capture the current screen and analyze it
    3. process_image_from_url(url)  — download an image from a URL and analyze it
    """

    def __init__(self):
        self.model = VLM_MODEL
        self.endpoint = f"{OLLAMA_URL}/generate"

    # ------------------------------------------------------------------
    # Core: send image bytes + prompt to local Ollama VLM
    # ------------------------------------------------------------------
    def _query_vlm(self, image_bytes: bytes, prompt: str) -> str:
        """Encode image and call the Ollama /generate endpoint."""
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [encoded],
            "stream": False,
        }
        try:
            response = requests.post(self.endpoint, json=payload, timeout=120)
            response.raise_for_status()
            return response.json().get("response", "[VLM] No response from model.")
        except Exception as e:
            return f"[VLM] Error querying model: {e}"

    # ------------------------------------------------------------------
    # Feature 1: Analyze a local image file
    # ------------------------------------------------------------------
    def process_image(self, image_path: str, prompt: str = "Describe this image in detail.") -> str:
        """
        Sends a local image file and a prompt to the local VLM (llama3.2-vision) via Ollama.
        Returns a text description.
        """
        if not os.path.exists(image_path):
            return f"[VLM] Error: Image not found at '{image_path}'"
        try:
            with open(image_path, "rb") as f:
                image_bytes = f.read()
            return self._query_vlm(image_bytes, prompt)
        except Exception as e:
            return f"[VLM] Error reading image file: {e}"

    # ------------------------------------------------------------------
    # Feature 2: Capture the screen and analyze it
    # ------------------------------------------------------------------
    def capture_screen(self, prompt: str = "Describe everything you see on this screen in detail. Identify all open applications, text, and relevant information.") -> str:
        """
        Takes a full-screen screenshot using 'mss', converts it to PNG bytes,
        and sends it to the local VLM for analysis.
        """
        try:
            import mss
            import mss.tools
            from PIL import Image
            import io

            with mss.mss() as sct:
                # Capture the primary monitor
                monitor = sct.monitors[1]
                screenshot = sct.grab(monitor)

                # Convert to PIL Image then to PNG bytes
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                image_bytes = buf.getvalue()

            print(f"[VLM] Screen captured ({len(image_bytes) // 1024} KB). Analyzing...")
            return self._query_vlm(image_bytes, prompt)

        except ImportError:
            return "[VLM] Screen capture requires 'mss' and 'Pillow'. Run: pip install mss Pillow"
        except Exception as e:
            return f"[VLM] Screen capture failed: {e}"

    # ------------------------------------------------------------------
    # Feature 3: Analyze an image from a URL
    # ------------------------------------------------------------------
    def process_image_from_url(self, url: str, prompt: str = "Describe this image in detail.") -> str:
        """
        Downloads an image from the given URL and sends it to the VLM.
        """
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            image_bytes = resp.content
            print(f"[VLM] Downloaded image from URL ({len(image_bytes) // 1024} KB). Analyzing...")
            return self._query_vlm(image_bytes, prompt)
        except Exception as e:
            return f"[VLM] Failed to download or process image from URL: {e}"

    # ------------------------------------------------------------------
    # Convenience: auto-detect what the user wants
    # ------------------------------------------------------------------
    def analyze(self, source: str, prompt: str = "Describe what you see in detail.") -> str:
        """
        Smart dispatcher:
        - 'screen' → capture the desktop
        - http(s)://... with image extension → download and analyze
        - local file path → read and analyze
        """
        src_lower = source.strip().lower()
        if src_lower in ("screen", "[screen]", "screenshot", "desktop"):
            return self.capture_screen(prompt)
        elif src_lower.startswith("http://") or src_lower.startswith("https://"):
            return self.process_image_from_url(source, prompt)
        else:
            return self.process_image(source, prompt)
