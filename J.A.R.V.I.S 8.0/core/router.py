import os
import yaml
import requests

import time

config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
with open(config_path, "r") as f:
    config = yaml.safe_load(f)

THRESHOLD = config.get("routing", {}).get("semantic_threshold", 0.7)
OLLAMA_URL = (
    config.get("models", {})
    .get("local", {})
    .get("endpoint", "http://localhost:11434/api")
)
SLM_MODEL = config.get("models", {}).get("local", {}).get("slm", "qwen2.5:7b")


class LLMRouter:
    _local_offline_until = 0

    def __init__(self):
        self.threshold = THRESHOLD

    def analyze_intent(self, query: str) -> dict:
        """
        Uses the local SLM to determine:
        1. Complexity (0.0 to 1.0)
        2. Intent (VISION, GENERAL, CODE)
        Returns a dict.
        """
        prompt = (
            "Analyze the following query and provide a JSON response with two fields:\n"
            "1. 'complexity': A float from 0.0 (simple) to 1.0 (complex).\n"
            "2. 'intent': One of ['VISION', 'GENERAL', 'CODE'].\n"
            "   Use 'VISION' if the user wants you to see, look, analyze the screen, room, or environment.\n"
            "   Use 'CODE' if the user is asking for specific coding help or specialist knowledge.\n"
            "   Use 'GENERAL' for everything else.\n\n"
            f"Query: '{query}'\n"
            "JSON ONLY:"
        )

        # Circuit Breaker: Skip if recently failed
        if time.time() < LLMRouter._local_offline_until:
            return {"complexity": 1.0, "intent": "GENERAL"}

        try:
            response = requests.post(
                f"{OLLAMA_URL}/generate",
                json={
                    "model": SLM_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                },
                timeout=15, # Increased to 15s to allow for model loading
            )
            response.raise_for_status()
            import json

            data = json.loads(response.json().get("response", "{}"))
            return {
                "complexity": float(data.get("complexity", 1.0)),
                "intent": data.get("intent", "GENERAL").upper(),
            }
        except Exception as e:
            print(
                f"[Router] Local SLM unavailable or timeout ({e}). Using heuristic fallback."
            )
            # Heuristic fallback for intent
            intent = "GENERAL"
            vision_indicators = ["see", "look", "analyse", "screen", "room", "camera", "webcam"]
            if any(kw in query.lower() for kw in vision_indicators):
                intent = "VISION"
            
            LLMRouter._local_offline_until = time.time() + 60 # Reduce failover to 1 min for faster recovery
            return {"complexity": 1.0, "intent": intent}

    def route(self, query: str) -> dict:
        """Returns a dict with 'provider' (NVIDIA_NIM/OLLAMA) and 'intent'."""
        analysis = self.analyze_intent(query)
        print(f"[Router] Analysis: {analysis}")

        provider = (
            "NVIDIA_NIM" if analysis["complexity"] > self.threshold else "OLLAMA"
        )
        return {"provider": provider, "intent": analysis["intent"]}
