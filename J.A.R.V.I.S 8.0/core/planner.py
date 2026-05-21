import os
import yaml
from openai import OpenAI
from typing import List, Optional
from core.memory_mhc import MHC_Memory


class Planner:
    def __init__(self, memory: MHC_Memory):
        self.memory = memory

        # Load config for models
        config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        self.api_key = os.getenv("NVIDIA_API_KEY")
        self.base_url = config.get("models", {}).get("cloud", {}).get("api_base")
        self.model = (
            config.get("models", {})
            .get("cloud", {})
            .get("lrm", "meta/llama-3.3-70b-instruct")
        )

        self._client = (
            OpenAI(base_url=self.base_url, api_key=self.api_key)
            if self.api_key
            else None
        )

        # Ensure plans directory exists
        self.plans_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "plans")
        )
        os.makedirs(self.plans_dir, exist_ok=True)

    def generate_autonomous_plans(self, context: str):
        """
        Determines if a new plan is needed for the authorized categories
        and generates it if appropriate.
        """
        if not self._client:
            return

        # Authorized Categories:
        # 1. Current Project (J.A.R.V.I.S 8.0)
        # 2. User Research commands (handled via orchestrator/researcher)
        # 3. Self-Evolution (performance/skills)
        # 4. Memory Insight (analyzing history)

        prompt = (
            "You are the JARVIS Selective Architect. Analyze the current system context and determine "
            "if there is a high-priority improvement needed for:\n"
            "1. J.A.R.V.I.S 8.0 core functionality.\n"
            "2. Skill development or performance optimization.\n"
            "3. Structural memory gaps.\n\n"
            f"CONTEXT:\n{context}\n\n"
            "If an improvement is needed, output a JSON object with: 'category', 'topic', and 'reason'. "
            "If NO urgent plan is needed, output 'NONE'. "
            "Limit your response to ONLY the JSON or 'NONE'."
        )

        try:
            completion = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=256,
            )
            response = completion.choices[0].message.content.strip()

            if response != "NONE":
                import json

                try:
                    plan_meta = json.loads(response)
                    self.create_personalized_plan(
                        plan_meta["topic"], plan_meta["category"], context
                    )
                except Exception:
                    pass
        except Exception:
            pass

    def create_personalized_plan(self, topic: str, category: str, context: str):
        """Generates a detailed, implementation-ready plan in the precise format."""
        if not self._client:
            return

        print(f"[Planner] Generating personalized plan for: {topic} ({category})")

        prompt = (
            f"You are JARVIS 8.0. Generate a precise, implementation-ready plan for the following topic: '{topic}' "
            f"in the category of '{category}'.\n\n"
            f"PERSONALIZED CONTEXT (from system memory):\n{context}\n\n"
            "### REQUIRED FORMAT:\n"
            "GOAL: A clear, one-sentence objective.\n"
            "WHY: Technical rationale and how it benefits the system/user.\n"
            "HOW: Step-by-step logic tree for implementation.\n"
            "IMPLEMENTATION: Provide REAL, ready-to-use Python code snippets specifically tailored for the Jarvis 8.0 MAOS codebase (using current core modules like MHC_Memory, Orchestrator, etc.).\n\n"
            "Output ONLY the markdown content."
        )

        try:
            completion = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=4096,
            )
            plan_content = completion.choices[0].message.content

            # Save to plans directory
            filename = topic.lower().replace(" ", "_").replace("/", "_") + "_plan.md"
            file_path = os.path.join(self.plans_dir, filename)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(plan_content)

            print(f"[Planner] Plan saved: plans/{filename}")
        except Exception as e:
            print(f"[Planner] Failed to generate plan: {e}")
