import os
import sys
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from core.sandbox import DockerSandbox
from core.cli_engine import CLIEngine

def main():
    load_dotenv()
    print("=== Testing J.A.R.V.I.S 10.0 Sandbox & CLI Engine ===")
    
    # 1. Initialize Sandbox
    sandbox = DockerSandbox()
    print("Ensuring container is running...")
    if not sandbox.ensure_container_running():
        print("[FAILED] Failed to start Docker sandbox. Make sure Docker is running on your system!")
        sys.exit(1)
        
    print("[SUCCESS] Sandbox running successfully!")

    # 2. Test execution of a basic command
    print("\nRunning a basic command: 'python --version'")
    res = sandbox.execute_command("python --version")
    print(f"Exit Code: {res['exit_code']}")
    print(f"Stdout: {res['stdout']}")
    print(f"Stderr: {res['stderr']}")
    
    if res["success"]:
        print("[SUCCESS] Basic execution succeeded!")
    else:
        print("[FAILED] Basic execution failed.")
        
    # 3. Test self-validation CLI Engine (without LLM)
    print("\nRunning CLI Engine with intentionally failing command (expecting failure since no LLM is passed)...")
    cli = CLIEngine(sandbox)
    fail_res = cli.execute_and_validate("python -c \"import nonexistent_package\"")
    print(f"Exit Code: {fail_res['exit_code']}")
    print(f"Success: {fail_res['success']}")
    print(f"Error captured: {fail_res['stderr']}")
    
    if not fail_res["success"] and "nonexistent_package" in fail_res["stderr"]:
        print("[SUCCESS] CLI captured traceback correctly!")
    else:
        print("[FAILED] Capture failure.")

if __name__ == "__main__":
    main()
