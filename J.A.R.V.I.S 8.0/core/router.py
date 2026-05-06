import os
import yaml
import requests

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
    def __init__(self):
        self.threshold = THRESHOLD

    def get_complexity_score(self, query: str) -> float:
        """
        Uses the local SLM to determine if the query is simple (e.g., 'hello', 'time')
        or complex (requires deep reasoning, planning, coding).
        Returns a float between 0.0 and 1.0.
        """
        prompt = (
            "Analyze the following query and rate its complexity from 0.0 to 1.0.\n"
            "0.0 means very simple (e.g., greetings, asking the time).\n"
            "1.0 means highly complex (e.g., writing code, complex reasoning, deep research).\n"
            "Reply with ONLY the floating point number.\n\n"
            f"Query: '{query}'"
        )

        try:
            response = requests.post(
                f"{OLLAMA_URL}/generate",
                json={"model": SLM_MODEL, "prompt": prompt, "stream": False},
                timeout=10,
            )
            response.raise_for_status()
            score_text = response.json().get("response", "1.0").strip()

            # Extract float from response if model gets chatty
            import re

            match = re.search(r"0\.[0-9]+|1\.0", score_text)
            if match:
                score = float(match.group(0))
            else:
                score = 1.0  # Default to cloud if unsure

            return min(max(score, 0.0), 1.0)
        except Exception as e:
            print(f"[Router] Error communicating with local SLM: {e}")
            return 1.0  # Default to cloud on failure to ensure capability

    def route(self, query: str) -> str:
        """Returns 'NVIDIA_NIM' or 'OLLAMA' based on query complexity."""
        score = self.get_complexity_score(query)
        print(f"[Router] Query complexity score: {score}")
        if score > self.threshold:
            return "NVIDIA_NIM"
        else:
            return "OLLAMA"
