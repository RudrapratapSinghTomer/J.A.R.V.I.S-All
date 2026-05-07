import os
import requests
import yaml
from openai import OpenAI
from dotenv import load_dotenv


def check_system():
    load_dotenv()
    print("=== Jarvis 8.0 System Diagnostics ===\n")

    # 1. Check Config
    config_path = "config.yaml"
    if not os.path.exists(config_path):
        print("[FAIL] config.yaml not found.")
        return

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    print("[OK] config.yaml loaded.")

    # 2. Check Ollama
    ollama_url = (
        config.get("models", {})
        .get("local", {})
        .get("endpoint", "http://localhost:11434/api")
    )
    slm_model = config.get("models", {}).get("local", {}).get("slm", "qwen2.5:7b")

    try:
        # Check if server is up
        base_url = ollama_url.replace("/api", "")
        resp = requests.get(base_url, timeout=5)
        if resp.status_code == 200:
            print(f"[OK] Ollama server reachable at {base_url}")
        else:
            print(f"[FAIL] Ollama server returned status {resp.status_code}")

        # Check if model is available
        resp = requests.get(f"{base_url}/api/tags")
        models = [m["name"] for m in resp.json().get("models", [])]
        if slm_model in models or f"{slm_model}:latest" in models:
            print(f"[OK] Local model '{slm_model}' is available.")
        else:
            print(
                f"[WARNING] Local model '{slm_model}' not found in Ollama. Found: {models}"
            )
    except Exception as e:
        print(f"[FAIL] Ollama check failed: {e}")

    # 3. Check NVIDIA NIM
    nvidia_key = os.getenv("NVIDIA_API_KEY")
    if not nvidia_key:
        print("[FAIL] NVIDIA_API_KEY not found in environment.")
    else:
        print(f"[OK] NVIDIA_API_KEY found (starts with {nvidia_key[:8]}...)")
        try:
            client = OpenAI(
                base_url="https://integrate.api.nvidia.com/v1", api_key=nvidia_key
            )
            model = (
                config.get("models", {})
                .get("cloud", {})
                .get("lrm", "meta/llama-3.1-70b-instruct")
            )
            # Simple test call
            completion = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=10,
            )
            print(f"[OK] NVIDIA NIM call successful with model '{model}'.")
        except Exception as e:
            print(f"[FAIL] NVIDIA NIM call failed: {e}")

    # 4. Check Google Gemini / Mem0
    google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("Gemini_API_KEY")
    if not google_key:
        print("[FAIL] GOOGLE_API_KEY / Gemini_API_KEY not found in environment.")
    else:
        print(f"[OK] Google/Gemini API Key found (starts with {google_key[:8]}...)")
        try:
            from google.genai import Client

            gemini_client = Client(api_key=google_key)
            # Use gemini-2.5-flash for test
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash", contents="ping"
            )
            print(f"[OK] Gemini API call successful with model 'gemini-2.5-flash'.")
        except Exception as e:
            print(f"[FAIL] Gemini API call failed: {e}")

    # 5. Check Mem0 Initialization
    try:
        from core.memory_mhc import MHC_Memory

        memory = MHC_Memory()
        if memory.memory is not None:
            print("[OK] Mem0 initialized successfully with Chroma.")
        else:
            print(
                "[WARNING] Mem0 initialized in fallback mode (JSONL). Check dependencies/Chroma."
            )
    except Exception as e:
        print(f"[FAIL] Mem0 initialization failed: {e}")

    print("\n=== Diagnostics Complete ===")


if __name__ == "__main__":
    check_system()
