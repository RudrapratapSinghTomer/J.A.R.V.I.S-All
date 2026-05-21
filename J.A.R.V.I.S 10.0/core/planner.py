import os
import json
import yaml
from openai import OpenAI
from typing import List, Dict, Optional

# Load config
_CONFIG_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "config.yaml"))
with open(_CONFIG_PATH, "r") as f:
    _CFG = yaml.safe_load(f)

class CognitivePlanner:
    """
    Cognitive Task Tree Planner.
    Generates structured execution plans and performs human-in-the-loop/self-validation
    cycles before execution begins.
    """
    def __init__(self, llm_client: OpenAI = None, model: str = "meta/llama-3.3-70b-instruct"):
        self.llm_client = llm_client
        self.model = model

    def generate_plan(self, query: str, system_context: str, past_episodes: List[dict]) -> dict:
        """Generates a structured task tree plan to resolve the user prompt."""
        if not self.llm_client:
            print("[Planner Warning] No LLM client. Using simple fallback plan.")
            return self._get_fallback_plan(query)

        episodes_str = json.dumps(past_episodes, indent=2) if past_episodes else "No past history."
        
        prompt = (
            "You are the J.A.R.V.I.S 10.0 Cognitive Architect.\n"
            "Formulate a highly efficient execution plan to solve the User Query.\n"
            "Your plan should utilize parallelization where possible (grouping tasks into independent steps).\n\n"
            f"USER QUERY: {query}\n\n"
            f"SYSTEM ENVIRONMENT CONTEXT:\n{system_context}\n\n"
            f"HISTORICAL MEMORY EPISODES (STM/LTM):\n{episodes_str}\n\n"
            "Generate a valid JSON object matching the schema below. "
            "Independent steps (no shared dependencies) will be run in parallel.\n\n"
            "### JSON Plan Schema:\n"
            "{\n"
            "  \"goal\": \"Overall plan goal\",\n"
            "  \"steps\": [\n"
            "    {\n"
            "      \"id\": 1,\n"
            "      \"type\": \"terminal | edit | browser | capability_acquirer\",\n"
            "      \"description\": \"Description of what this step does\",\n"
            "      \"command_or_action\": \"The actual shell command or action logic to run\",\n"
            "      \"dependencies\": []\n"
            "    }\n"
            "  ]\n"
            "}\n"
            "Output ONLY the JSON object. Do not wrap in markdown tags or include any trailing/leading text."
        )

        try:
            completion = self.llm_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            
            raw_text = completion.choices[0].message.content
            plan = json.loads(raw_text)
            
            # Auto-validate the plan tree structure
            if self.validate_plan_tree(plan):
                return plan
            else:
                print("[Planner Warning] First-draft plan failed tree validation. Re-generating...")
                return self.generate_plan(query, system_context, past_episodes)
                
        except Exception as e:
            print(f"[Planner Error] Failed to generate plan using LLM: {e}")
            return self._get_fallback_plan(query)

    def validate_plan_tree(self, plan: dict) -> bool:
        """Performs internal consistency checks on the generated plan tree."""
        if not plan or "steps" not in plan:
            return False
            
        steps = plan.get("steps", [])
        if not steps:
            return False

        registered_ids = {step.get("id") for step in steps}
        
        for step in steps:
            # Check mandatory fields
            if not all(k in step for k in ["id", "type", "description", "command_or_action", "dependencies"]):
                return False
                
            # Verify dependency IDs exist in the plan tree to prevent deadlocks
            deps = step.get("dependencies", [])
            for dep in deps:
                if dep not in registered_ids:
                    print(f"[Planner Tree Validation Failed] Step {step.get('id')} has unresolved dependency {dep}")
                    return False
                    
        return True

    def _get_fallback_plan(self, query: str) -> dict:
        """Returns a generic sequential plan structure on planning failures."""
        return {
            "goal": f"Process query: {query}",
            "steps": [
                {
                    "id": 1,
                    "type": "terminal",
                    "description": "Fallback shell execution",
                    "command_or_action": query,
                    "dependencies": []
                }
            ]
        }
