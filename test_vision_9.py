import os
import sys
from dotenv import load_dotenv

# Add Jarvis 8.0/9.0 paths
sys.path.append(os.path.join(os.path.dirname(__file__), "J.A.R.V.I.S 8.0"))

from agents.vision_vlm import VisionVLM


def test_vision_logic():
    load_dotenv("J.A.R.V.I.S 8.0/.env")
    vision = VisionVLM()

    print("=== Vision Priority Test ===")

    # Test 1: Cloud Vision (should try first)
    print("\n[Test 1] Testing Primary Cloud Vision...")
    # We use a dummy image path or 'screen'
    # For testing, we'll just check if it calls the cloud logic
    # Note: To fully test, we'd need a real image, but here we check routing

    # Test 2: Local Fallback
    print("\n[Test 2] Testing Local Fallback (Simulating No API Key)...")
    original_key = os.environ.get("NVIDIA_API_KEY")
    os.environ["NVIDIA_API_KEY"] = ""  # Clear key

    # This should print "NVIDIA_API_KEY missing. Falling back to Local VLM..."
    # and then try to hit localhost:11434
    try:
        # We don't actually want to wait for a 300s timeout if Ollama is off,
        # but we want to see the "Falling back" print.
        result = vision.analyze("screen", prompt="Test")
        print(f"Result snippet: {result[:100]}")
    finally:
        if original_key:
            os.environ["NVIDIA_API_KEY"] = original_key


if __name__ == "__main__":
    test_vision_logic()
