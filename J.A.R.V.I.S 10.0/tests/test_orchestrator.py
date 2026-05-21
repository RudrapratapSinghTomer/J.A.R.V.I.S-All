import os
import sys
import asyncio
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from core.sandbox import DockerSandbox
from core.cli_engine import CLIEngine
from core.memory import SystemContextMemory, AgentMemory
from core.planner import CognitivePlanner
from core.orchestrator import DualLoopOrchestrator

async def main():
    load_dotenv()
    print("=== Testing J.A.R.V.I.S 10.0 Dual-Loop Orchestration ===")

    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    # 1. Initialize Components
    sandbox = DockerSandbox()
    cli_engine = CLIEngine(sandbox)
    sys_memory = SystemContextMemory(workspace_dir)
    agent_memory = AgentMemory("CoreOrchestrator")
    
    # Clean LTM for fresh testing
    if os.path.exists(agent_memory.ltm_path):
        os.remove(agent_memory.ltm_path)
    agent_memory = AgentMemory("CoreOrchestrator")

    # Use no-LLM Planner fallback simulation
    planner = CognitivePlanner()
    
    # Build orchestrator (without LLM for offline validation test)
    orchestrator = DualLoopOrchestrator(
        planner=planner,
        cli_engine=cli_engine,
        sys_memory=sys_memory,
        agent_memory=agent_memory
    )

    # 2. Simulate a Custom Plan with Parallelism
    # We create a plan with two independent steps, and step 3 depending on both
    print("\nSimulating plan with parallel execution capabilities...")
    test_plan = {
        "goal": "Verify parallel command orchestration",
        "steps": [
            {
                "id": 1,
                "type": "terminal",
                "description": "Execute Task 1 (Sleeps 1s)",
                "command_or_action": "python -c \"import time; print('Task 1 Executing'); time.sleep(1); print('Task 1 Done')\"",
                "dependencies": []
            },
            {
                "id": 2,
                "type": "terminal",
                "description": "Execute Task 2 (Sleeps 1s)",
                "command_or_action": "python -c \"import time; print('Task 2 Executing'); time.sleep(1); print('Task 2 Done')\"",
                "dependencies": []
            },
            {
                "id": 3,
                "type": "terminal",
                "description": "Execute Task 3 (Consolidator dependent on both)",
                "command_or_action": "python -c \"print('Task 3 Consolidated successfully!')\"",
                "dependencies": [1, 2]
            }
        ]
    }

    # Override orchestrator planner mock return
    planner.generate_plan = lambda q, ctx, past: test_plan

    # 3. Run Orchestrator Async Cycle
    import time
    start_time = time.time()
    
    result = await orchestrator.run("Run parallel performance verification test")
    
    end_time = time.time()
    elapsed = end_time - start_time
    
    print("\nFinal Orchestrator Summary:")
    print("---------------------------------")
    print(result)
    print("---------------------------------")
    print(f"Elapsed Time: {elapsed:.2f} seconds")
    
    # Since Task 1 (1s sleep) and Task 2 (1s sleep) ran in parallel,
    # the total time for the execution loop should be close to ~1.0s (rather than 2.0s sequential).
    if elapsed < 1.8:
        print("[SUCCESS] Orchestrator successfully ran Tasks 1 and 2 in parallel!")
    else:
        print("[FAILED] Orchestrator ran tasks sequentially.")

if __name__ == "__main__":
    asyncio.run(main())
