import os
from openai import OpenAI


class Planner:
    def __init__(self):
        self.api_key = os.environ.get("NVIDIA_API_KEY", "")
        self.client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1", api_key=self.api_key
        )
        self.model = "meta/llama-3.1-70b-instruct"  # Fallback mapping for NIM, update to Kimi K2.6 when catalog is synced

        self.plans_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "plans"
        )
        os.makedirs(self.plans_dir, exist_ok=True)

    def generate_plan(self, feature: dict, jarvis_9_state: str, stop_event=None):
        """
        Evaluates a feature and generates a plan file in the plans/ directory.
        """
        if stop_event and stop_event.is_set():
            return
        # Create a safe filename
        safe_name = "".join(
            [
                c
                for c in feature["feature_name"]
                if c.isalpha() or c.isdigit() or c == " "
            ]
        ).rstrip()
        plan_filename = safe_name.lower().replace(" ", "_") + "_plan.md"
        plan_path = os.path.join(self.plans_dir, plan_filename)

        if os.path.exists(plan_path):
            print(f"Plan for {feature['feature_name']} already exists.")
            return

        prompt = f"""
You are the Sovereign Architect for J.A.R.V.I.S 9.0.
Your task is to integrate a valuable feature from an older version into J.A.R.V.I.S 9.0's codebase.

Target Feature: {feature["feature_name"]}
From Version: {feature["source_version"]}
Description: {feature["description"]}

Current J.A.R.V.I.S 9.0 capability state overview:
{jarvis_9_state}

Create a detailed implementation plan in Markdown. Use the following structure exactly:

# Implementation Plan: {feature["feature_name"]}

## What
(Explain what the feature is and what components it involves)

## Why
(Explain why J.A.R.V.I.S 9.0 needs this)

## How
(Step-by-step technical implementation guide, including file paths and code snippets tailored for J.A.R.V.I.S 9.0)
"""
        print(f"Planning implementation for {feature['feature_name']}...")
        if not self.api_key:
            print("WARNING: NVIDIA_API_KEY not set. Generating stub plan instead.")
            with open(plan_path, "w", encoding="utf-8") as f:
                f.write(
                    f"# Implementation Plan: {feature['feature_name']}\\n\\n[Awaiting NVIDIA API Key to generate full plan]"
                )
            return

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a master AI software architect.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=4000,
            )
            content = response.choices[0].message.content

            with open(plan_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Plan generated at: {plan_path}")
        except Exception as e:
            print(f"Planner failed for {feature['feature_name']}: {e}")
