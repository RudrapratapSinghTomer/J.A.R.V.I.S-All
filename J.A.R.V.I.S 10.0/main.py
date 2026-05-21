import os
import sys
import asyncio
from dotenv import load_dotenv
from openai import OpenAI

# Ensure J.A.R.V.I.S 10.0 core is in the import path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.sandbox import DockerSandbox
from core.cli_engine import CLIEngine
from core.browser import WebBridgeBrowser
from core.capability_acquirer import CapabilityAcquirer
from core.memory import SystemContextMemory, AgentMemory
from core.planner import CognitivePlanner
from core.orchestrator import DualLoopOrchestrator

def print_banner():
    print("\n" + "=" * 60)
    print("      J.A.R.V.I.S 10.0 — Universal Agentic Core (Project X)")
    print("=" * 60)
    print("  Capabilities:")
    print("    • Dual-Loop Parallel Validation Orchestrator")
    print("    • Self-Validating CLI with Sandbox Subprocess Fallback")
    print("    • Multi-Layer STM/LTM & High-Level System Context Memory")
    print("    • Kimi WebBridge Browser & Document Scraping")
    print("    • Human-in-the-Loop Capability Acquisition Plan Review")
    print("=" * 60)
    print("  Special Command Syntax:")
    print("    propose <capability>     — Autonomous research & draft integration plan")
    print("    approve <capability>     — Confirm and execute approved capability installation")
    print("    exit / quit              — Shut down")
    print("=" * 60 + "\n")

async def main():
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
    print_banner()

    # 1. Initialize NVIDIA Cloud LLM Client if API Key is available
    nvidia_key = os.getenv("NVIDIA_API_KEY")
    llm_client = None
    model_name = os.getenv("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")
    
    if nvidia_key:
        try:
            llm_client = OpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=nvidia_key
            )
            print("[System] Cloud LRM Client initialized successfully.")
        except Exception as e:
            print(f"[System Warning] Failed to initialize Cloud LRM Client: {e}")
    else:
        print("[System Info] NVIDIA_API_KEY not found in environment. Operating in offline/local-fallback mode.")

    # 2. Build Core Subsystems
    workspace_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
    
    sandbox = DockerSandbox()
    cli_engine = CLIEngine(sandbox, llm_client, model=model_name)
    browser = WebBridgeBrowser()
    acquirer = CapabilityAcquirer(browser, cli_engine, llm_client, model=model_name)
    
    sys_memory = SystemContextMemory(workspace_root, sandbox=sandbox)
    agent_memory = AgentMemory("CoreAgent")
    
    planner = CognitivePlanner(llm_client, model=model_name)
    orchestrator = DualLoopOrchestrator(
        planner=planner,
        cli_engine=cli_engine,
        sys_memory=sys_memory,
        agent_memory=agent_memory,
        llm_client=llm_client,
        model=model_name
    )

    user_id = os.getenv("JARVIS_USER", "developer")

    # 3. Main Command Loop
    while True:
        try:
            query = input(f"[{user_id}]> ").strip()
            
            if not query:
                continue

            if query.lower() in ["exit", "quit"]:
                print("[JARVIS] Gracefully stopping sandbox container. Goodbye.")
                sandbox.stop_container()
                break

            # --- Human-in-the-Loop Capability Hooks ---
            if query.lower().startswith("propose "):
                capability = query[len("propose "):].strip()
                if not capability:
                    print("[JARVIS] Please specify a capability name. E.g. 'propose Image Classification'")
                    continue
                    
                print(f"[JARVIS] Initiating dynamic research for '{capability}'...")
                plan_path = acquirer.propose_capability_plan(capability, "Acquire capability matching user request")
                
                print(f"\n[JARVIS] SUCCESS: Integration Plan checklist created!")
                print(f"[JARVIS] Location: {plan_path}")
                print(f"[JARVIS] Please review the plan in your editor. When satisfied, run: 'approve {capability}'\n")
                continue

            elif query.lower().startswith("approve "):
                capability = query[len("approve "):].strip()
                if not capability:
                    print("[JARVIS] Please specify the capability name to approve. E.g. 'approve Image Classification'")
                    continue
                    
                plan_filename = f"{capability.lower().replace(' ', '_')}_plan.json"
                plan_path = os.path.normpath(os.path.join(workspace_root, "J.A.R.V.I.S 10.0", "capabilities", "plans", plan_filename))
                
                if not os.path.exists(plan_path):
                    print(f"[JARVIS] No active draft plan found for '{capability}' at: {plan_path}")
                    continue
                    
                print(f"[JARVIS] Executing approved capability installation for '{capability}'...")
                res = acquirer.execute_and_install_capability(plan_path)
                
                if res.get("success"):
                    print(f"\n[JARVIS] SUCCESS: {res.get('message')}")
                    print(f"[JARVIS] Registry updated. New skill '{capability}' is now natively active!\n")
                else:
                    print(f"\n[JARVIS] FAILED: {res.get('error')}\n")
                continue

            # --- Standard Query Orchestration Loop ---
            print("\n[Jarvis Processing...]\n")
            
            # Run query asynchronously through parallelized orchestrator
            response = await orchestrator.run(query, user_id=user_id)
            print(f"\n[JARVIS]> {response}\n")

        except KeyboardInterrupt:
            print("\n[JARVIS] Interrupted. Goodbye.")
            sandbox.stop_container()
            break
        except Exception as e:
            print(f"\n[System Error] {e}\n")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
