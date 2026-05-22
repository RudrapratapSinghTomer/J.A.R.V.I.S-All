import os
import json
from openai import OpenAI
from typing import List, Dict, Optional
from core.config_loader import load_config
from core.cognitive_engine import TrueBackendThinkingEngine

# Load config
_CFG = load_config()

class CognitivePlanner:
    """
    Cognitive Task Tree Planner.
    Generates structured execution plans and performs human-in-the-loop/self-validation
    cycles before execution begins.
    """
    def __init__(self, llm_client: OpenAI = None, model: str = "meta/llama-3.3-70b-instruct"):
        self.llm_client = llm_client
        self.model = model
        self.engine = TrueBackendThinkingEngine(llm_client, model)

    def generate_plan(self, query: str, system_context: str, past_episodes: List[dict], _retries: int = 0) -> dict:
        """Generates an advanced structured task tree plan after executing a 13-stage cognitive analysis."""
        max_retries = 2
        cognitive_output = self.engine.analyze_and_plan(query, system_context, past_episodes)
        
        # Extract the synthesized plan from Stage 11
        plan = cognitive_output.get("stage_11_plan_synthesis", {})
        
        # Enrich the plan with the adaptive execution directives from Stage 13 and critique from Stage 12
        plan["adaptive_execution"] = cognitive_output.get("stage_13_adaptive_execution", {})
        plan["plan_critique"] = cognitive_output.get("stage_12_plan_critique", {})
        plan["cognitive_state"] = cognitive_output.get("cognitive_state", {})
        
        # Log backend thinking output beautifully
        print("\n" + "=" * 60)
        print("                 TRUE BACKEND THINKING ARCHITECTURE")
        print("=" * 60)
        cs = plan["cognitive_state"]
        print(f"  [Cognitive Type] : {cs.get('stage_4_cognitive_type', {}).get('required_cognition_profile', 'Unknown')}")
        print(f"  [Surface Intent] : {cs.get('stage_3_intent_decomposition', {}).get('surface_intent', 'N/A')}")
        print(f"  [Strategic Goal] : {cs.get('stage_3_intent_decomposition', {}).get('actual_strategic_goal', 'N/A')}")
        print(f"  [Uncertainty Map]: Knowns={len(cs.get('stage_5_uncertainty_map', {}).get('known_knowns', []))}, Unknowns={len(cs.get('stage_5_uncertainty_map', {}).get('known_unknowns', []))}")
        print(f"  [Hard Constraint]: {cs.get('stage_6_constraint_discovery', {}).get('hard_constraints', ['None'])[0]}")
        print(f"  [Failure Model]  : {cs.get('stage_8_failure_prediction', {}).get('what_could_fail', 'N/A')}")
        print(f"  [Self-Critique]  : Verdict='{plan['plan_critique'].get('critique_verdict', 'N/A')}'")
        print(f"  [Adaptive Plan]  : Max Retries={plan['adaptive_execution'].get('max_retries_per_step', 7)}")
        print("=" * 60 + "\n")

        # Validate the plan tree structure
        if self.validate_plan_tree(plan):
            return plan
        else:
            if _retries < max_retries:
                print(f"[Planner Warning] Plan tree validation failed. Regenerating (attempt {_retries + 1}/{max_retries})...")
                return self.generate_plan(query, system_context, past_episodes, _retries=_retries + 1)
            else:
                print(f"[Planner Warning] Plan tree validation failed after {max_retries} retries. Using fallback plan.")
                return self._get_fallback_plan(query)

    def validate_plan_tree(self, plan: dict) -> bool:
        """Performs internal consistency checks on the generated plan tree."""
        if not plan or "steps" not in plan:
            return False
            
        steps = plan.get("steps", [])
        if not steps:
            return False

        # Coerce registered step IDs to strings to ensure consistent types
        registered_ids = {str(step.get("id")) for step in steps}
        
        for step in steps:
            # Check mandatory fields
            if not all(k in step for k in ["id", "type", "description", "command_or_action", "dependencies"]):
                return False
                
            # Verify dependency IDs exist in the plan tree to prevent deadlocks
            deps = step.get("dependencies", [])
            for dep in deps:
                if str(dep) not in registered_ids:
                    print(f"[Planner Tree Validation Failed] Step {step.get('id')} has unresolved dependency {dep}")
                    return False
                    
        return True

    def _get_fallback_plan(self, query: str) -> dict:
        """
        Returns a safe fallback plan with no executable steps.
        The orchestrator will detect the empty steps and generate a direct LLM response instead.
        This prevents raw natural language from being executed as shell commands on host or guest.
        """
        return {
            "goal": f"Process query: {query}",
            "steps": []
        }

