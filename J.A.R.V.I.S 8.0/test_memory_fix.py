import os
from core.memory_mhc import MHC_Memory


def test_memory():
    print("Initializing MHC_Memory...")
    memory = MHC_Memory()
    print("Adding a test memory...")
    # This should trigger extraction and embedding
    memory.add_to_manifold("test_user", "Today I learned that Jarvis 8.0 is modular.")
    print("Search test...")
    res = memory.get_context("test_user", "What did I learn?")
    print(f"Result: {res}")


if __name__ == "__main__":
    # Mock environment if needed
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    test_memory()
