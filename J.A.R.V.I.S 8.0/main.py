import os
import sys

# Ensure jarvis-os directory is in the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.router import LLMRouter
from core.memory_mhc import MHC_Memory
from core.orchestrator import Orchestrator
from agents.researcher import AutoResearcher
from agents.executor_lam import ExecutorLAM


from dotenv import load_dotenv


def main():
    load_dotenv()
    print("Initializing Jarvis 8.0 MAOS...")

    # Initialize Core Components
    router = LLMRouter()
    mhc_memory = MHC_Memory()

    # Initialize Agents
    researcher = AutoResearcher()
    executor = ExecutorLAM()

    # Initialize Orchestrator
    jarvis = Orchestrator(router, mhc_memory, researcher, executor)

    print("\n" + "=" * 50)
    print("Jarvis 8.0 Online.")
    print("Type 'exit' or 'quit' to terminate.")
    print("=" * 50 + "\n")

    user_id = "developer"  # Default user

    while True:
        try:
            query = input(f"[{user_id}]> ")
            if query.lower() in ["exit", "quit"]:
                break

            if not query.strip():
                continue

            print("\n[Jarvis Processing...]")
            response = jarvis.run(query, user_id=user_id)

            print(f"\n[Jarvis]> {response}\n")

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"\n[System Error] {e}\n")


if __name__ == "__main__":
    main()
