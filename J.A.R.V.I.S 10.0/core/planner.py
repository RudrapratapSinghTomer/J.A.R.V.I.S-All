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

    def generate_plan(self, query: str, system_context: str, past_episodes: List[dict], _retries: int = 0, validation_errors: List[str] = None) -> dict:
        """Generates an advanced structured task tree plan after executing a 13-stage cognitive analysis."""
        max_retries = 2
        if validation_errors is None:
            validation_errors = []

        # If previous attempts failed validation, pass errors to context so LLM self-corrects
        current_context = system_context
        if validation_errors:
            error_notes = "\n=== PREVIOUS PLAN VALIDATION FAILURES ===\n" + "\n".join(
                f"- Attempt {i+1} Failure: {err}" for i, err in enumerate(validation_errors)
            ) + "\nYour previous plan was rejected due to these structural errors. Correct them in the new plan.\n"
            current_context += error_notes

        cognitive_output = self.engine.analyze_and_plan(query, current_context, past_episodes)
        
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
        success, error_msg = self.validate_plan_tree_with_error(plan)
        if success:
            return plan
        else:
            validation_errors.append(error_msg)
            if _retries < max_retries:
                print(f"[Planner Warning] Plan tree validation failed: '{error_msg}'. Regenerating (attempt {_retries + 1}/{max_retries})...")
                return self.generate_plan(query, system_context, past_episodes, _retries=_retries + 1, validation_errors=validation_errors)
            else:
                print(f"[Planner Warning] Plan tree validation failed after {max_retries} retries. Using fallback plan.")
                return self._get_fallback_plan(query)

    def validate_plan_tree(self, plan: dict) -> bool:
        """Performs internal consistency checks on the generated plan tree."""
        success, _ = self.validate_plan_tree_with_error(plan)
        return success

    def validate_plan_tree_with_error(self, plan: dict) -> tuple:
        """Performs internal consistency checks on the generated plan tree and returns (success, error_msg)."""
        if not plan or "steps" not in plan:
            return False, "Plan structure is missing or empty"
            
        steps = plan.get("steps", [])
        if not steps:
            return False, "Plan has no executable steps"

        # Coerce registered step IDs to strings to ensure consistent types
        registered_ids = {str(step.get("id")) for step in steps}
        
        for step in steps:
            # Check mandatory fields
            if not all(k in step for k in ["id", "type", "description", "command_or_action", "dependencies"]):
                return False, f"Step {step.get('id', 'unknown')} is missing mandatory fields"
                
            # Verify dependency IDs exist in the plan tree to prevent deadlocks
            deps = step.get("dependencies", [])
            for dep in deps:
                dep_str = str(dep)
                if dep_str not in registered_ids:
                    # If it is numeric or starts with "step", it is intended to be a step ID but is missing.
                    # Otherwise, it represents a conceptual requirement (e.g. "transformers library") and is ignored.
                    is_step_reference = dep_str.isdigit() or dep_str.lower().startswith("step")
                    if is_step_reference:
                        err_msg = f"Step {step.get('id')} has unresolved step dependency '{dep}'"
                        print(f"[Planner Tree Validation Failed] {err_msg}")
                        return False, err_msg
                    else:
                        print(f"[Planner Tree Validation Warning] Step {step.get('id')} lists conceptual prerequisite '{dep}' (ignored for scheduling)")
                    
        return True, ""

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

