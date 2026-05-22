import os
import base64
import time
import requests
from openai import OpenAI

# Try importing cv2 safely
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

class WebcamCapture:
    """
    Hardware-level Webcam capture utility for J.A.R.V.I.S 10.0.
    Captures a frame on-demand without holding persistent threads or locks.
    """
    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index

    def capture(self, save_path: str = None) -> dict:
        """
        Captures a single frame from the webcam, encodes to JPEG bytes,
        and optionally saves it to disk. Releases resources immediately.
        """
        if not CV2_AVAILABLE:
            return {
                "success": False,
                "image_bytes": None,
                "save_path": None,
                "error": "OpenCV (cv2) is not installed in the host/guest environment."
            }

        # Try VideoCapture with DSHOW on Windows to minimize latency, fallback to default
        print(f"[Vision] Opening webcam index {self.camera_index}...")
        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            print("[Vision] CAP_DSHOW failed, falling back to default MSMF/V4L2...")
            cap = cv2.VideoCapture(self.camera_index)

        if not cap.isOpened():
            return {
                "success": False,
                "image_bytes": None,
                "save_path": None,
                "error": f"Could not open webcam index {self.camera_index}."
            }

        try:
            # Set buffer size to 1 to prevent getting old cached frames
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

            # Let the camera warm up/auto-expose briefly (grab a few frames)
            for _ in range(5):
                cap.grab()
                time.sleep(0.05)

            ret, frame = cap.read()
            if not ret or frame is None:
                return {
                    "success": False,
                    "image_bytes": None,
                    "save_path": None,
                    "error": "Failed to read a valid frame from the webcam."
                }

            # Encode to JPEG
            success, buffer = cv2.imencode(".jpg", frame)
            if not success:
                return {
                    "success": False,
                    "image_bytes": None,
                    "save_path": None,
                    "error": "Failed to encode frame to JPEG format."
                }

            image_bytes = buffer.tobytes()

            # Handle saving to file if requested
            if save_path:
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, "wb") as f:
                    f.write(image_bytes)
                print(f"[Vision] Captured webcam frame saved to: {save_path}")

            return {
                "success": True,
                "image_bytes": image_bytes,
                "save_path": save_path,
                "error": None
            }

        finally:
            cap.release()
            print("[Vision] Webcam released.")

    @classmethod
    def probe_available(cls, camera_index: int = 0) -> bool:
        """Helper to quickly check if a webcam device is available and openable."""
        if not CV2_AVAILABLE:
            return False
        try:
            cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap = cv2.VideoCapture(camera_index)
            if cap.isOpened():
                cap.release()
                return True
        except Exception:
            pass
        return False

class VisionAnalyzer:
    """
    Vision-Language-Model interface for J.A.R.V.I.S 10.0.
    Uses NVIDIA Cloud NIM VLM by default with a local Ollama fallback.
    """
    def __init__(self, llm_client: OpenAI = None, cloud_model: str = "meta/llama-3.2-90b-vision-instruct",
                 local_endpoint: str = "http://127.0.0.1:11434/api", local_model: str = "llama3.2-vision:11b"):
        self.llm_client = llm_client
        self.cloud_model = cloud_model
        self.local_endpoint = local_endpoint
        self.local_model = local_model
        self.webcam = WebcamCapture()

    def analyze_image(self, image_bytes: bytes, prompt: str) -> str:
        """
        Sends the image bytes and text prompt to the VLM.
        Tries Cloud NIM first, then local Ollama fallback.
        """
        encoded_image = base64.b64encode(image_bytes).decode("utf-8")

        # 1. Attempt Cloud VLM if client is initialized
        if self.llm_client and os.getenv("NVIDIA_API_KEY"):
            try:
                print(f"[Vision] Sending image to Cloud VLM ({self.cloud_model})...")
                completion = self.llm_client.chat.completions.create(
                    model=self.cloud_model,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{encoded_image}"
                                    }
                                }
                            ]
                        }
                    ],
                    max_tokens=1024
                )
                response_text = completion.choices[0].message.content
                print("[Vision] Received Cloud VLM response.")
                return response_text
            except Exception as e:
                print(f"[Vision Warning] Cloud VLM request failed: {e}. Falling back to local Ollama...")

        # 2. Local Fallback via Ollama
        try:
            print(f"[Vision] Sending image to local VLM ({self.local_model} via {self.local_endpoint})...")
            url = f"{self.local_endpoint}/generate"
            payload = {
                "model": self.local_model,
                "prompt": prompt,
                "images": [encoded_image],
                "stream": False
            }
            response = requests.post(url, json=payload, timeout=90)
            response.raise_for_status()
            response_text = response.json().get("response", "No response content from local VLM.")
            print("[Vision] Received local VLM response.")
            return response_text
        except Exception as local_err:
            return f"Vision Analysis Failed. Both Cloud VLM and local fallback failed. Error: {local_err}"

    def capture_and_analyze(self, prompt: str, save_path: str = None) -> dict:
        """
        Captures a webcam frame and runs VLM analysis on it.
        """
        if not save_path:
            # Save to capabilities/screenshots by default with unique timestamp to prevent overwriting
            repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            save_path = os.path.join(repo_dir, "capabilities", "screenshots", f"webcam_{timestamp}.jpg")

        cap_res = self.webcam.capture(save_path=save_path)
        if not cap_res["success"]:
            return {
                "success": False,
                "analysis": None,
                "save_path": None,
                "error": cap_res["error"]
            }

        analysis = self.analyze_image(cap_res["image_bytes"], prompt)
        return {
            "success": True,
            "analysis": analysis,
            "save_path": save_path,
            "error": None
        }
