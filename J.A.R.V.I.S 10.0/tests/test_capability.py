import os
import sys
import json
import shutil
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from core.sandbox import DockerSandbox
from core.cli_engine import CLIEngine
from core.browser import WebBridgeBrowser
from core.capability_acquirer import CapabilityAcquirer

def main():
    load_dotenv()
    print("=== Testing J.A.R.V.I.S 10.0 Capability Review Flow ===")

    # Initialize environment
    sandbox = DockerSandbox()
    cli_engine = CLIEngine(sandbox)
    browser = WebBridgeBrowser()
    
    acquirer = CapabilityAcquirer(browser, cli_engine)

    # 1. Clean dynamic files to ensure fresh environment
    plans_dir = os.path.dirname(acquirer.propose_capability_plan("dummy", ""))
    plugins_dir = os.path.join(os.path.dirname(plans_dir), "plugins")
    registry_file = os.path.join(os.path.dirname(plans_dir), "registry.json")
    
    if os.path.exists(plans_dir):
        shutil.rmtree(plans_dir)
    if os.path.exists(plugins_dir):
        shutil.rmtree(plugins_dir)
    if os.path.exists(registry_file):
        os.remove(registry_file)
        
    # Re-initialize to recreate dirs
    acquirer = CapabilityAcquirer(browser, cli_engine)

    # 2. Propose a plan for Speech Synthesis
    print("\n[Step 1] Requesting new capability: 'Speech Synthesis'...")
    plan_path = acquirer.propose_capability_plan(
        capability_name="Speech Synthesis",
        task_description="Convert written text strings into clean spoken wave audio files using transformers pipeline"
    )
    
    print(f"Plan drafted and saved to: {plan_path}")
    
    # Verify file exists
    if os.path.exists(plan_path):
        print("[SUCCESS] Capability plan JSON file created successfully!")
    else:
        print("[FAILED] Plan file not found.")
        sys.exit(1)

    # Read and inspect the plan status
    with open(plan_path, "r") as f:
        plan_data = json.load(f)
        
    print("\nDrafted Plan Context:")
    print("---------------------------------")
    print(f"Capability: {plan_data.get('capability')}")
    print(f"Goal: {plan_data.get('goal')}")
    print(f"Hugging Face Model: {plan_data.get('huggingface_model')}")
    print(f"Dependencies: {plan_data.get('dependencies')}")
    print(f"Checklist tasks: {plan_data.get('checklist')}")
    print(f"Plan Status: {plan_data.get('status')}")
    print("---------------------------------")

    if plan_data.get("status") == "AWAITING_REVIEW":
        print("[SUCCESS] J.A.R.V.I.S successfully paused for user review and approval!")
    else:
        print("[FAILED] Plan status incorrect.")

    # 3. Simulate User Approval and Installation
    print("\n[Step 2] Simulating User Approval. Commencing Installation Flow...")
    install_res = acquirer.execute_and_install_capability(plan_path)
    
    print(f"Installation Success Status: {install_res.get('success')}")
    print(f"Message: {install_res.get('message') or install_res.get('error')}")

    if install_res.get("success"):
        print("[SUCCESS] Capability installed and verified in sandbox!")
        
        # Verify dynamic plugin exists
        plugin_path = install_res.get("plugin_path")
        if os.path.exists(plugin_path):
            print(f"[SUCCESS] Plugin file generated at: {plugin_path}")
        else:
            print("[FAILED] Plugin file missing.")
            
        # Verify capability registration
        with open(registry_file, "r") as f:
            registry = json.load(f)
        print(f"Registry Contents: {json.dumps(registry, indent=2)}")
        
        if "speech_synthesis" in registry.get("capabilities", {}):
            print("[SUCCESS] Capability successfully indexed in dynamic registry!")
        else:
            print("[FAILED] Capability missing from index.")
    else:
        print("[FAILED] Installation execution failed.")

if __name__ == "__main__":
    main()
