import os
import sys

# Add parent directory to path
sys.path.append(os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from core.memory import SystemContextMemory, AgentMemory
from core.sandbox import DockerSandbox

def main():
    print("=== Testing J.A.R.V.I.S 10.0 Dual-Layer Memory Engine ===")

    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    # 1. Test System Context Memory
    print("\n[Test 1] Initializing System Context Memory...")
    sandbox = DockerSandbox()
    sys_mem = SystemContextMemory(workspace_dir, sandbox=sandbox)
    sys_mem.register_active_document(os.path.join(workspace_dir, "config.yaml"))
    sys_mem.register_active_document(os.path.join(workspace_dir, "requirements.txt"))
    
    compiled = sys_mem.compile_global_context("Active Sandbox")
    print("Compiled Context Output:")
    print("---------------------------------")
    print(compiled)
    print("---------------------------------")
    
    if "config.yaml" in compiled and "requirements.txt" in compiled:
        print("[SUCCESS] System context compiled successfully!")
    else:
        print("[FAILED] System context missing file registrations.")

    # 2. Test Agent Memory (STM & LTM)
    print("\n[Test 2] Initializing Agent Memory for 'Researcher'...")
    agent_mem = AgentMemory("Researcher")
    
    # Clean old files to ensure fresh test
    if os.path.exists(agent_mem.ltm_path):
        os.remove(agent_mem.ltm_path)
    # Reload fresh
    agent_mem = AgentMemory("Researcher")

    # Test STM
    print("Adding conversation turns to STM...")
    agent_mem.add_to_stm("user", "Hello Jarvis!")
    agent_mem.add_to_stm("assistant", "Hello! How can I help you today?")
    stm_list = agent_mem.get_stm_as_list()
    print(f"STM Turns: {len(stm_list)}")
    if len(stm_list) == 2:
        print("[SUCCESS] STM working perfectly!")
    else:
        print("[FAILED] STM turns count mismatch.")

    # Test LTM Save & Query Search
    print("\nAdding execution records to LTM...")
    agent_mem.add_to_ltm(
        query="identify object in picture",
        resolution="Searched Hugging Face, downloaded yolo, wrote test, validated success.",
        code_snippets=["import cv2", "import torch"]
    )
    agent_mem.add_to_ltm(
        query="text to speech synthesis",
        resolution="Acquired whisper models and synthesizers.",
        code_snippets=["from transformers import pipeline"]
    )

    print("Searching LTM for 'object'...")
    search_res = agent_mem.search_ltm("I need to find an object inside this file")
    print(f"Search Results Found: {len(search_res)}")
    for i, res in enumerate(search_res):
        print(f"Match {i+1}: Query='{res['query']}', Resolution='{res['resolution']}'")

    if len(search_res) > 0 and "object" in search_res[0]["query"]:
        print("[SUCCESS] Semantic LTM retrieval working perfectly!")
    else:
        print("[FAILED] LTM search retrieval mismatch.")

if __name__ == "__main__":
    main()
