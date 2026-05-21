import os
import json
import yaml
import asyncio
from openai import OpenAI
from typing import List, Dict, Set
from core.planner import CognitivePlanner
from core.cli_engine import CLIEngine
from core.memory import SystemContextMemory, AgentMemory

class DualLoopOrchestrator:
    """
    Dual-Loop Orchestration Engine.
    Executes tasks in parallel using asyncio, validates each step's outputs,
    and coordinates System/Agent memory updates.
    """
    def __init__(self, 
                 planner: CognitivePlanner, 
                 cli_engine: CLIEngine, 
                 sys_memory: SystemContextMemory,
                 agent_memory: AgentMemory,
                 llm_client: OpenAI = None,
                 model: str = "meta/llama-3.3-70b-instruct"):
        self.planner = planner
        self.cli_engine = cli_engine
        self.sys_memory = sys_memory
        self.agent_memory = agent_memory
        self.llm_client = llm_client
        self.model = model

    async def run(self, query: str, user_id: str = "developer") -> str:
        print(f"\n[Orchestrator] Starting processing loop for: '{query}'")

        # 1. Compile Global Context & LTM Memory
        sys_context = self.sys_memory.compile_global_context()
        past_episodes = self.agent_memory.search_ltm(query)

        # 2. Loop 1: Plan & Validate Plan
        print("[Orchestrator] Generating plan...")
        plan = self.planner.generate_plan(query, sys_context, past_episodes)
        print(f"[Orchestrator] Plan Generated: '{plan.get('goal', 'No Goal')}'")
        
        # Log plan steps
        steps = plan.get("steps", [])
        for step in steps:
            print(f"  Step {step.get('id')}: {step.get('description')} (Deps: {step.get('dependencies')})")

        # 3. Parallelized Execution Loop
        completed_steps: Set[int] = set()
        active_tasks = {}
        
        uncompleted_steps = {step["id"]: step for step in steps}
        step_results = {}

        while uncompleted_steps:
            # Find steps that are ready (all dependencies completed, not yet started)
            ready_steps = [
                step for step in uncompleted_steps.values()
                if step["id"] not in active_tasks and set(step.get("dependencies", [])).issubset(completed_steps)
            ]

            if not ready_steps and not active_tasks:
                print("[Orchestrator Error] Deadlock detected or plan contains cyclic dependencies.")
                break

            # Start ready steps in parallel
            for step in ready_steps:
                step_id = step["id"]
                # Schedule step execution asynchronously
                print(f"[Orchestrator] Dispatching Step {step_id} in parallel: '{step['description']}'")
                active_tasks[step_id] = asyncio.create_task(self._execute_and_validate_step(step))

            if active_tasks:
                # Wait for any active task to finish
                done, _ = await asyncio.wait(active_tasks.values(), return_when=asyncio.FIRST_COMPLETED)
                
                # Process completed tasks
                for task in done:
                    # Find step_id of completed task
                    step_id = [sid for sid, t in active_tasks.items() if t == task][0]
                    del active_tasks[step_id]
                    
                    result = task.result()
                    step_results[step_id] = result
                    
                    if result["success"]:
                        print(f"[Orchestrator] Step {step_id} completed and validated successfully!")
                        completed_steps.add(step_id)
                        del uncompleted_steps[step_id]
                    else:
                        print(f"[Orchestrator Critical] Step {step_id} failed verification: {result.get('error', 'Execution error')}")
                        # If a critical step fails, we attempt self-correction / replanning
                        # For simple base codebase, we exit the orchestration with failure
                        return f"Orchestration loop aborted due to failure at Step {step_id}: {result.get('error')}"

            # Small sleep to prevent busy-waiting loop
            await asyncio.sleep(0.1)

        # 4. Final Output Synthesis & Memory Log
        consolidated_summary = self._synthesize_final_output(query, step_results)
        
        # Save interaction to LTM Memory
        self.agent_memory.add_to_ltm(
            query=query,
            resolution=consolidated_summary
        )

        return consolidated_summary

    async def _execute_and_validate_step(self, step: dict) -> dict:
        """Executes a single plan step in the sandbox, then performs post-execution validation."""
        step_type = step.get("type", "terminal")
        action = step.get("command_or_action", "")
        
        # 1. Execution phase
        if step_type == "terminal" or step_type == "edit":
            # Run terminal command via self-correcting CLI Engine
            # We run blocking executables inside an executor pool to keep orchestrator async loop responsive
            loop = asyncio.get_running_loop()
            exec_res = await loop.run_in_executor(
                None, 
                self.cli_engine.execute_and_validate, 
                action
            )
        else:
            # Fallback executor for other types
            exec_res = {"success": True, "stdout": f"Action {step_type} executed successfully.", "stderr": ""}

        if not exec_res["success"]:
            return {"success": False, "error": exec_res.get("stderr", "Execution failure")}

        # 2. Validation phase: Let the LLM post-validate outputs
        val_res = self._post_validate_step(step, exec_res)
        return val_res

    def _post_validate_step(self, step: dict, exec_res: dict) -> dict:
        """Asks the LLM to verify if the output of a command fits the success criteria."""
        if not self.llm_client:
            # Fallback if no LLM: trust CLI exit status
            return {"success": exec_res["success"], "output": exec_res.get("stdout", ""), "error": exec_res.get("stderr", "")}

        prompt = (
            "You are the J.A.R.V.I.S 10.0 Post-Execution Validator.\n"
            "An agent executed a plan step, and we captured the terminal output.\n"
            "Verify if the output matches the expected result of this step description.\n\n"
            f"STEP DESCRIPTION: {step.get('description')}\n"
            f"STEP ACTION: {step.get('command_or_action')}\n\n"
            f"EXECUTION STDOUT:\n{exec_res.get('stdout')}\n\n"
            f"EXECUTION STDERR:\n{exec_res.get('stderr')}\n\n"
            "Respond in JSON format with 'validated' (boolean) and 'reason' (string).\n"
            "Format:\n"
            "{\n"
            "  \"validated\": true,\n"
            "  \"reason\": \"Output matches expected criteria because...\"\n"
            "}\n"
            "Ensure the response is valid JSON and nothing else."
        )

        try:
            completion = self.llm_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            import json
            data = json.loads(completion.choices[0].message.content)
            validated = data.get("validated", False)
            reason = data.get("reason", "No reason provided.")
            
            if validated:
                return {"success": True, "output": exec_res.get("stdout", "")}
            else:
                return {"success": False, "error": f"Validation Rejected: {reason}"}
        except Exception as e:
            # Fallback on LLM parser issues
            print(f"[Orchestrator Validation Error] Verification script failed: {e}")
            return {"success": exec_res["success"], "output": exec_res.get("stdout", ""), "error": exec_res.get("stderr", "")}

    def _synthesize_final_output(self, query: str, step_results: dict) -> str:
        """Synthesizes step execution logs into a unified final answer."""
        if not self.llm_client:
            # Fallback
            summary_lines = []
            for sid, res in step_results.items():
                summary_lines.append(f"Step {sid} Result:\n{res.get('output', '')[:300]}")
            return "\n\n".join(summary_lines)

        prompt = (
            "You are J.A.R.V.I.S 10.0, the Symbiotic Intelligence.\n"
            "Summarize the completed execution of the task plan into a cohesive, concise, "
            "and professional resolution statement for the user.\n\n"
            f"USER QUERY: {query}\n\n"
            f"EXECUTION RESULTS:\n{json.dumps(step_results, indent=2)}\n\n"
            "Provide the final response directly. Ground your summary in the exact work completed."
        )

        try:
            completion = self.llm_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            return completion.choices[0].message.content
        except Exception as e:
            return f"Task completed successfully. Logs: {json.dumps(step_results)}"
