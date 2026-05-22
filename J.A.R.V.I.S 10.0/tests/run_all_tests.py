import os
import sys
import subprocess
import time

# Ensure J.A.R.V.I.S 10.0 is in path
sys.path.append(os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

def run_test_file(filename: str) -> bool:
    print(f"\n=======================================================")
    print(f"  RUNNING TEST SUITE: {filename}")
    print(f"=======================================================")
    
    test_path = os.path.normpath(os.path.join(os.path.dirname(__file__), filename))
    
    start_time = time.time()
    result = subprocess.run([sys.executable, "-u", test_path], capture_output=False, timeout=120)
    elapsed = time.time() - start_time
    
    success = result.returncode == 0
    status_str = "SUCCESS" if success else "FAILED"
    print(f"-------------------------------------------------------")
    print(f"  RESULT: {status_str} (Elapsed: {elapsed:.2f}s)")
    print(f"=======================================================\n")
    return success

def main():
    print("=======================================================")
    print("      J.A.R.V.I.S 10.0 — INTEGRATION VERIFICATION RUNNER")
    print("=======================================================")
    
    test_suites = [
        "test_sandbox.py",
        "test_memory.py",
        "test_browser.py",
        "test_orchestrator.py",
        "test_capability.py",
        "test_cognitive.py",
        "test_antigravity.py",
        "test_kimi_browser.py",
        "test_audio.py",
        "test_vision.py"
    ]
    
    passed_count = 0
    total_count = len(test_suites)
    
    for test in test_suites:
        if run_test_file(test):
            passed_count += 1
            
    print("\n" + "=" * 55)
    print("                 FINAL VERIFICATION REPORT")
    print("=" * 55)
    print(f"  Total Test Suites Run : {total_count}")
    print(f"  Passed                : {passed_count}")
    print(f"  Failed                : {total_count - passed_count}")
    print("=" * 55)
    
    if passed_count == total_count:
        print("  SYSTEM HEALTH: PERFECT - ALL SUBSYSTEMS GREEN!")
        print("=" * 55 + "\n")
        sys.exit(0)
    else:
        print("  SYSTEM HEALTH: DEGRADED - VERIFY LOG TRACEBACKS!")
        print("=" * 55 + "\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
