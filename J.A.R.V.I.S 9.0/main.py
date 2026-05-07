import os
import sys
import threading
from dotenv import load_dotenv

# Ensure core is in path
sys.path.append(os.path.join(os.path.dirname(__file__), "core"))

from core.evolution import EvolutionCore


def main():
    # Load environment variables
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

    print("\n" + "=" * 60)
    print("  J.A.R.V.I.S 9.0 — Sovereign Architect Evolution")
    print("=" * 60)
    print("  Status: Idle Analysis Loop starting in background...")
    print("=" * 60 + "\n")

    # --- Setup Background Consciousness ---
    stop_event = threading.Event()
    evolution = EvolutionCore(stop_event)

    # Start evolution in background thread
    evolve_thread = threading.Thread(target=evolution.run_cycle, daemon=True)
    evolve_thread.start()

    user_id = os.getenv("JARVIS_USER", "developer")

    try:
        while True:
            # We are waiting for input -> System is Idle
            # But EvolutionCore is already running by default.

            query = input(f"[{user_id}]> ").strip()

            if not query:
                continue

            # Command received -> Pause Background Analysis
            evolution.pause()

            if query.lower() in ["exit", "quit"]:
                print("[JARVIS] Shutting down evolution. Goodbye.")
                stop_event.set()
                break

            print("\n[Jarvis Processing...]\n")
            # For now, Jarvis 9.0 is focused on the Evolution loop.
            # We can add a simple responder here or integrate 8.0 orchestrator.
            print(
                f"[JARVIS]> I am currently focused on analyzing legacy versions. I have paused background scanning to process your command: '{query}'\n"
            )

            # Command finished -> Resume Background Analysis
            evolution.resume()

    except KeyboardInterrupt:
        print("\n[JARVIS] Evolution interrupted. Shutting down.")
        stop_event.set()


if __name__ == "__main__":
    main()
