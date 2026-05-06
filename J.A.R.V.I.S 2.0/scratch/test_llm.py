import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()

from core.mind import Mind
from agents.base import AgentTask


async def test_llm():
    print("Testing LLM connectivity...")
    mind = Mind.default()

    # Test HEAVY capability (likely NVIDIA or Gemini)
    print("Sending request to HEAVY brain...")
    try:
        response = await mind.llm_client.generate(
            "Say 'Neural Core Nominal'.", capability="heavy", purpose="test"
        )
        print(f"Response: {response.text}")
        print(f"Model ID: {response.model_id} ({response.provider})")
    except Exception as e:
        print(f"FAILED: {e}")


if __name__ == "__main__":
    asyncio.run(test_llm())
