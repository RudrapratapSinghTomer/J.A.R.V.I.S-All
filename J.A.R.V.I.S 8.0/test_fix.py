import os
from dotenv import load_dotenv
from core.memory_mhc import MHC_Memory


def test_fix():
    load_dotenv()
    print("Testing MHC Memory with text-embedding-004...")
    memory = MHC_Memory()
    if memory.memory:
        try:
            memory.add_to_manifold("system", "Test memory after model fix.")
            print("SUCCESS: Memory added successfully.")
        except Exception as e:
            print(f"FAILED: {e}")
    else:
        print("FAILED: Memory not initialized.")


if __name__ == "__main__":
    test_fix()
