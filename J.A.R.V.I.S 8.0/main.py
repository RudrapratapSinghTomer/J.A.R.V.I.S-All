import os

os.environ["LANGCHAIN_TRACING_V2"] = "false"
import sys

# Ensure jarvis 8.0 directory is in the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from core.router import LLMRouter
from core.memory_mhc import MHC_Memory
from core.orchestrator import Orchestrator
from agents.researcher import AutoResearcher
from agents.executor_lam import ExecutorLAM
from agents.vision_vlm import VisionVLM
from core.consciousness import BackgroundConsciousness
import threading


def main():
    load_dotenv()
    print("Initializing Jarvis 8.0 MAOS...")

    # --- Core Components ---
    router = LLMRouter()
    mhc_memory = MHC_Memory()

    # --- Agents ---
    researcher = AutoResearcher()
    executor = ExecutorLAM()
    vision = VisionVLM()

    # --- Background Consciousness ---
    stop_event = threading.Event()
    consciousness = BackgroundConsciousness(stop_event, mhc_memory)
    consciousness_thread = threading.Thread(target=consciousness.start, daemon=True)
    consciousness_thread.start()

    # --- Background Monitor ---
    from core.monitor import SystemMonitor

    monitor = SystemMonitor()
    monitor_thread = threading.Thread(target=monitor.start, daemon=True)
    monitor_thread.start()

    # --- Orchestrator (all components wired) ---
    jarvis = Orchestrator(router, mhc_memory, researcher, executor, vision=vision)

    print("\n" + "=" * 60)
    print("  J.A.R.V.I.S 8.0 — Modular Agentic Operating System")
    print("=" * 60)
    print("  Commands:")
    print("    [screen] <question>       — Analyze your live screen + webcam (PiP)")
    print("    [image: <path/url>] <q>   — Analyze a specific image")
    print("    research <topic>          — Deep recursive web research")
    print("    exit / quit               — Shut down")
    print("=" * 60 + "\n")

    user_id = os.getenv("JARVIS_USER", "developer")

    while True:
        try:
            # User is about to type, pause background consciousness to free resources
            consciousness.pause()

            query = input(f"[{user_id}]> ").strip()

            if query.lower() in ["exit", "quit"]:
                print("[JARVIS] Shutting down. Goodbye.")
                stop_event.set()
                vision.stop()  # Clean up vision threads
                break

            if not query:
                consciousness.resume()
                continue

            print("\n[Jarvis Processing...]\n")
            response = jarvis.run(query, user_id=user_id)

            print(f"[JARVIS]> {response}\n")

            # Action complete, resume background evolution
            consciousness.resume()

        except KeyboardInterrupt:
            print("\n[JARVIS] Interrupted. Shutting down.")
            stop_event.set()
            vision.stop()
            break
        except Exception as e:
            print(f"\n[System Error] {e}\n")
            consciousness.resume()


if __name__ == "__main__":
    main()
