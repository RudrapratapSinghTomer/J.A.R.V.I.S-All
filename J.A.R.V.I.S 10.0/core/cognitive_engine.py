import os
import json
from openai import OpenAI
from typing import List, Dict
from core.persona import get_persona  # Phase 1: persona & context injection

class TrueBackendThinkingEngine:
    """
    True Backend Thinking Engine for J.A.R.V.I.S 10.0.
    Implements the 13-stage advanced thinking loop to stabilize inputs, model reality,
    route cognitive strategies, discover constraints, map uncertainty, and run pre-execution critiques.
    """
    def __init__(self, llm_client: OpenAI = None, model: str = "meta/llama-3.3-70b-instruct"):
        self.llm_client = llm_client
        self.model = model

    def analyze_and_plan(self, query: str, system_context: str, past_episodes: List[dict]) -> dict:
        """
        Executes the full 13-stage advanced thinking process.
        Returns a dictionary containing the Cognitive Analysis and synthesized adaptive Plan.
        """
        print(f"\n[Backend Thinking] Initiating 13-Stage Cognitive Loop...")
        print("[Thinking] STAGE 1-3: Stabilizing Query, Modeling Reality, & Decomposing Intent...")
        print("[Thinking] STAGE 4-7: Identifying Cognitive Type, Mapping Uncertainty, Mapping Constraints...")
        print("[Thinking] STAGE 8-10: Modeling Capabilities, Predicting Failures, Routing Strategic Philosophy...")

        if not self.llm_client:
            print("[Backend Thinking Warning] Offline fallback mode active. Generating local cognitive state...")
            return self._generate_fallback_cognitive_state(query)

        episodes_str = json.dumps(past_episodes, indent=2) if past_episodes else "No past history."

        prompt = (
            "You are the J.A.R.V.I.S 10.0 Advanced Cognitive Reasoning Core.\n"
            "Process the User Query using the explicit 13-Stage Thinking Architecture.\n"
            "Build an internal reality model, map uncertainties/constraints, simulate failures, "
            "synthesize a parallel-capable plan, critique it adversarially, and inject adaptive execution rollback triggers.\n"
            "IMPORTANT: Carefully extract and honor all explicit OUTPUT requirements, target file paths, formats, and directories specified by the user (e.g. 'OUTPUT: create a plan at <path>'). Ensure the generated plan steps focus precisely on creating, writing, and formatting the requested output files at the exact locations specified, rather than trying to perform separate complex background actions autonomously unless requested.\n"
            "IMPORTANT: When asked to search the web, scrape sites, or browse, you MUST use the built-in 'browser' step type. Do NOT write Python scripts (e.g. requests/bs4) for web tasks.\n"
            "IMPORTANT: When asked to take a picture, capture webcam, identify objects, or look at the user, you MUST use the built-in 'vision' step type. Do NOT write custom Python scripts with opencv or tensorflow to capture or analyze webcam images.\n"
            "IMPORTANT: When the user asks to analyze, update memory with, or refers to an EXISTING image file name in their prompt (e.g., 'webcam_capture.jpg', 'snapshot.png'), you MUST use the 'vision' step type with the 'analyze_existing <image_path> <prompt>' action format. Do NOT capture a new webcam picture if they ask to analyze an existing image.\n"
            "IMPORTANT: You are aware of the pre-built Antigravity awesome-skills available in the system context. For any complex task, check if there is a relative pre-built skill in the AVAILABLE PRE-BUILT AWESOME SKILLS (ANTIGRAVITY) section. If a relevant skill exists, recommend its installation/activation (via 'propose antigravity <skill_name>' and 'approve antigravity <skill_name>' commands) as a plan step before running it, rather than writing ad-hoc code.\n\n"
            f"USER QUERY: {query}\n\n"
            f"SYSTEM ENVIRONMENT CONTEXT:\n{system_context}\n\n"
            f"HISTORICAL MEMORY EPISODES:\n{episodes_str}\n\n"
            "Output a single valid JSON block conforming exactly to the schema below. "
            "Do not include any conversational text or markdown code block markers. Just pure JSON.\n\n"
            "### JSON Output Schema:\n"
            "{\n"
            "  \"cognitive_state\": {\n"
            "    \"stage_1_query_stabilization\": {\n"
            "      \"explicit_request\": \"string\",\n"
            "      \"implied_request\": \"string\",\n"
            "      \"not_stated\": \"string\",\n"
            "      \"underspecified_fields\": [\"string\"]\n"
            "    },\n"
            "    \"stage_2_reality_model\": {\n"
            "      \"world_state\": \"string\",\n"
            "      \"environment_state\": \"string\",\n"
            "      \"constraints\": \"string\"\n"
            "    },\n"
            "    \"stage_3_intent_decomposition\": {\n"
            "      \"surface_intent\": \"string\",\n"
            "      \"actual_strategic_goal\": \"string\"\n"
            "    },\n"
            "    \"stage_4_cognitive_type\": {\n"
            "      \"required_cognition_profile\": \"Deterministic | Exploratory | Systems | Probabilistic | Constraint | Debugging | Design\"\n"
            "    },\n"
            "    \"stage_5_uncertainty_map\": {\n"
            "      \"known_knowns\": [\"string\"],\n"
            "      \"known_unknowns\": [\"string\"],\n"
            "      \"assumptions\": [\"string\"],\n"
            "      \"dependencies_missing\": [\"string\"]\n"
            "    },\n"
            "    \"stage_6_constraint_discovery\": {\n"
            "      \"hard_constraints\": [\"string\"],\n"
            "      \"soft_constraints\": [\"string\"],\n"
            "      \"hidden_constraints\": [\"string\"]\n"
            "    },\n"
            "    \"stage_7_capability_modeling\": {\n"
            "      \"available_tools\": [\"string\"],\n"
            "      \"failure_likelihood\": \"string\"\n"
            "    },\n"
            "    \"stage_8_failure_prediction\": {\n"
            "      \"what_could_fail\": \"string\",\n"
            "      \"defensive_mitigation\": \"string\"\n"
            "    },\n"
            "    \"stage_9_strategy_selection\": {\n"
            "      \"cognition_route\": \"Linear | Tree Search | ReAct | Verification-first | Simulation-first\"\n"
            "    },\n"
            "    \"stage_10_execution_philosophy\": {\n"
            "      \"primary_metric_optimization\": \"correctness | speed | exploration | cost\"\n"
            "    }\n"
            "  },\n"
            "  \"stage_11_plan_synthesis\": {\n"
            "    \"goal\": \"Overall synthesized plan objective\",\n"
            "    \"steps\": [\n"
            "      {\n"
            "        \"id\": 1,\n"
            "        \"type\": \"terminal | edit | browser | capability_acquirer | plugin | vision\",\n"
            "        \"description\": \"Description of step actions\",\n"
            "        \"command_or_action\": \"The exact, concrete executable action to perform. If type=terminal, this MUST be a valid, executable shell command or python script (e.g. 'python tests/test_memory.py' or 'mkdir plans'). NEVER specify natural language descriptions or pseudocode as terminal commands. If type=edit, this must be a script or tool command to create/modify a file. If type=vision, use 'capture_and_analyze <prompt>' or 'analyze_existing <image_path> <prompt>'. If type=browser, use 'search <term>' or 'navigate to <url>'\",\n"
            "        \"dependencies\": []\n"
            "      }\n"
            "    ]\n"
            "  },\n"
            "  \"stage_12_plan_critique\": {\n"
            "    \"is_overcomplicated\": false,\n"
            "    \"critique_verdict\": \"string\",\n"
            "    \"refinement_action\": \"string\"\n"
            "  },\n"
            "  \"stage_13_adaptive_execution\": {\n"
            "    \"max_retries_per_step\": 7,\n"
            "    \"rollback_triggers\": [\"string\"],\n"
            "    \"rollback_command_or_action\": \"string\"\n"
            "  }\n"
            "}"
        )

        try:
            # Phase 1: prepend persona system message so the planner always knows
            # who JARVIS is and who the user is before generating any plan.
            persona_msg = get_persona().get_system_message()

            completion = self.llm_client.chat.completions.create(
                model=self.model,
                messages=[persona_msg, {"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            raw_text = completion.choices[0].message.content
            cognitive_output = json.loads(raw_text)
            
            print("[Thinking] STAGE 11-12: Synthesizing Plan Tree & Running Adversarial Self-Critique...")
            print("[Thinking] STAGE 13: Compiling Dynamic Adaptive Rollbacks...")
            print(f"[Backend Thinking] Successfully generated cognitive plan for: '{query}'")
            return cognitive_output
            
        except Exception as e:
            # Retry without response_format in case the API doesn't support it
            if "response_format" in str(e).lower() or "unsupported" in str(e).lower():
                try:
                    completion = self.llm_client.chat.completions.create(
                        model=self.model,
                        messages=[persona_msg, {"role": "user", "content": prompt}],
                        temperature=0.1
                    )
                    raw_text = completion.choices[0].message.content
                    cognitive_output = json.loads(raw_text)
                    print(f"[Backend Thinking] Successfully generated cognitive plan for: '{query}' (without response_format)")
                    return cognitive_output
                except Exception as retry_e:
                    print(f"[Backend Thinking Error] Retry also failed: {retry_e}")
            print(f"[Backend Thinking Error] LLM cognitive planning failed: {e}. Falling back...")
            return self._generate_fallback_cognitive_state(query)

    def _generate_fallback_cognitive_state(self, query: str) -> dict:
        """Fallback mock cognitive state builder for clean offline resilience."""
        return {
            "cognitive_state": {
                "stage_1_query_stabilization": {
                    "explicit_request": query,
                    "implied_request": "Execute dynamic target command or capability action",
                    "not_stated": "System execution logs",
                    "underspecified_fields": []
                },
                "stage_2_reality_model": {
                    "world_state": "Offline mode / subprocess execution active",
                    "environment_state": "Windows 10 Local environment",
                    "constraints": "Offline limitations"
                },
                "stage_3_intent_decomposition": {
                    "surface_intent": query,
                    "actual_strategic_goal": f"Process offline execution of '{query}'"
                },
                "stage_4_cognitive_type": {
                    "required_cognition_profile": "Deterministic"
                },
                "stage_5_uncertainty_map": {
                    "known_knowns": ["Query execution string"],
                    "known_unknowns": ["System output metrics"],
                    "assumptions": ["Executing environment supports query requirements"],
                    "dependencies_missing": []
                },
                "stage_6_constraint_discovery": {
                    "hard_constraints": ["Subprocess timeout limits (60s)"],
                    "soft_constraints": ["High speed"],
                    "hidden_constraints": ["User manual intervention fallback"]
                },
                "stage_7_capability_modeling": {
                    "available_tools": ["Host terminal subprocess execution"],
                    "failure_likelihood": "Low"
                },
                "stage_8_failure_prediction": {
                    "what_could_fail": "Command not found or package import exceptions",
                    "defensive_mitigation": "CLI execution validation checks"
                },
                "stage_9_strategy_selection": {
                    "cognition_route": "Linear"
                },
                "stage_10_execution_philosophy": {
                    "primary_metric_optimization": "speed"
                }
            },
            "stage_11_plan_synthesis": {
                "goal": f"Execute target: {query}",
                "steps": [
                    {
                        "id": 1,
                        "type": "terminal",
                        "description": "Fallback shell execution",
                        "command_or_action": query,
                        "dependencies": []
                    }
                ]
            },
            "stage_12_plan_critique": {
                "is_overcomplicated": False,
                "critique_verdict": "Direct execution is appropriate for simple fallback commands.",
                "refinement_action": "Proceed directly"
            },
            "stage_13_adaptive_execution": {
                "max_retries_per_step": 3,
                "rollback_triggers": ["Command returned exit code non-zero"],
                "rollback_command_or_action": "echo 'Process failed. Re-evaluating environment.'"
            }
        }
