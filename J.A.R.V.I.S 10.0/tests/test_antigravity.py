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
    print("=== Testing J.A.R.V.I.S 10.0 Antigravity Skill Integration ===")

    # Initialize environment
    sandbox = DockerSandbox()
    cli_engine = CLIEngine(sandbox)
    browser = WebBridgeBrowser()
    acquirer = CapabilityAcquirer(browser, cli_engine)

    # 1. Clean dynamic plans/plugins to ensure clean state
    plans_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "capabilities", "plans"))
    plugins_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "capabilities", "plugins"))
    registry_file = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "capabilities", "registry.json"))

    # Force loader to discover skills (it has already cloned the repo)
    print("\n[Step 1] Loading and discovering Antigravity awesome-skills library...")
    skills = acquirer.antigravity_loader.discover_available_skills()
    assert len(skills) > 0, "No skills loaded from awesome-skills index!"
    print(f"[SUCCESS] Discovered {len(skills)} skills in awesome-skills library!")

    # 2. Test search and filtering
    print("\n[Step 2] Testing keyword search and filtering...")
    results = acquirer.antigravity_loader.filter_skills_by_query("security")
    assert len(results) > 0
    print(f"[SUCCESS] Filtered skills for 'security': found {len(results)} matches! (First match: {results[0]['name']})")

    # 3. Test Proposing Antigravity Skill Integration
    print("\n[Step 3] Proposing Integration of 'ad-creative' Skill...")
    plan_path = acquirer.propose_antigravity_skill_integration("ad-creative")
    assert plan_path is not None
    assert os.path.exists(plan_path)
    
    with open(plan_path, "r", encoding="utf-8") as f:
        plan_data = json.load(f)
    assert plan_data.get("capability") == "ad-creative"
    assert plan_data.get("source") == "antigravity"
    assert plan_data.get("status") == "AWAITING_REVIEW"
    print(f"[SUCCESS] Successfully created and structured plan for 'ad-creative' at {plan_path}!")

    # 4. Test Installing and Synthesizing Dynamic Plugin Wrapper
    print("\n[Step 4] Executing dynamic plugin wrapper synthesis & testing...")
    install_res = acquirer.execute_antigravity_skill_installation(plan_path)
    assert install_res.get("success") is True
    
    plugin_path = install_res.get("plugin_path")
    assert os.path.exists(plugin_path)
    print(f"[SUCCESS] Synthesized dynamic Python plugin wrapper at: {plugin_path}")

    # Read registry and verify
    with open(registry_file, "r", encoding="utf-8") as f:
        registry = json.load(f)
    assert "ad_creative" in registry.get("capabilities", {})
    print("[SUCCESS] Dynamic Antigravity skill successfully registered and verified!")

if __name__ == "__main__":
    main()
