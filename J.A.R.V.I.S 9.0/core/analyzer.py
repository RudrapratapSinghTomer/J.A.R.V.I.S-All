import os
import json
from openai import OpenAI


class Analyzer:
    def __init__(self):
        self.api_key = os.environ.get("NVIDIA_API_KEY", "")
        self.client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1", api_key=self.api_key
        )
        self.model = "meta/llama-3.1-70b-instruct"  # Fallback mapping for NIM or standard OpenAI compatible path, replace with deepseek-v4-pro if available in catalog

    def analyze_codebase(self, version_name: str, files_dict: dict) -> list:
        """
        Sends the codebase to the NIM API to extract a list of features.
        Returns a list of feature dictionaries.
        """
        code_context = ""
        for filepath, content in files_dict.items():
            code_context += f"\\n\\n--- FILE: {filepath} ---\\n{content}"

        prompt = f"""
Analyze the following codebase for {version_name}.
Identify the key autonomous, architectural, or agentic features implemented in this version.
Return ONLY a valid JSON list of objects, where each object has:
- "feature_name": string
- "description": string (what it does and why it's valuable)
- "source_version": "{version_name}"

Codebase Context:
{code_context[:350000]}
"""
        print(f"[{version_name}] Sending {len(code_context)} chars to Analyzer...")

        if not self.api_key:
            print("WARNING: NVIDIA_API_KEY not set. Skipping analysis.")
            return []

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a senior AI architect. Always output strictly valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=4000,
            )
            content = response.choices[0].message.content
            if content.startswith("```json"):
                content = content[7:-3]
            elif content.startswith("```"):
                content = content[3:-3]

            return json.loads(content.strip())
        except Exception as e:
            print(f"Analyzer failed for {version_name}: {e}")
            return []
