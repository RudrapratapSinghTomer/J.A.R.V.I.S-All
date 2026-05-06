import os
import yaml
import requests
import base64

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
    def __init__(self):
        self.model = VLM_MODEL
        self.endpoint = f"{OLLAMA_URL}/generate"

    def process_image(
        self, image_path: str, prompt: str = "Describe this image."
    ) -> str:
        """
        Sends an image and a prompt to the local VLM (Llama3.2-Vision) via Ollama.
        """
        if not os.path.exists(image_path):
            return f"[VLM] Error: Image not found at {image_path}"

        try:
            with open(image_path, "rb") as image_file:
                # Encode image to base64
                encoded_string = base64.b64encode(image_file.read()).decode("utf-8")

            payload = {
                "model": self.model,
                "prompt": prompt,
                "images": [encoded_string],
                "stream": False,
            }

            response = requests.post(
                self.endpoint, json=payload, timeout=60
            )  # Give it 60s
            response.raise_for_status()

            return response.json().get("response", "")
        except Exception as e:
            return f"[VLM] Error processing image: {e}"
