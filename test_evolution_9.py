import os
import sys
import time
import threading
from dotenv import load_dotenv

# Add core to path
sys.path.append(os.path.join(os.path.dirname(__file__), "J.A.R.V.I.S 9.0", "core"))

from evolution import EvolutionCore


def test_evolution_concurrency():
    load_dotenv("J.A.R.V.I.S 9.0/.env")

    print("=== Jarvis 9.0 Evolution Concurrency Test ===")

    stop_event = threading.Event()
    evolution = EvolutionCore(stop_event)

    # Start evolution in background
    evolve_thread = threading.Thread(target=evolution.run_cycle, daemon=True)
    evolve_thread.start()

    print("\n[Main] Background thread started. System is Idle.")
    time.sleep(5)  # Let it run for a bit

    print("\n[Main] Simulating USER COMMAND...")
    evolution.pause()
    print("[Main] Command processing (sleeping 3s)...")
    time.sleep(3)

    print("\n[Main] Command finished. Resuming background...")
    evolution.resume()
    time.sleep(5)  # Let it run more

    print("\n[Main] Test complete. Stopping background thread.")
    stop_event.set()
    time.sleep(2)
    print("=== Test Success ===")


if __name__ == "__main__":
    test_evolution_concurrency()
