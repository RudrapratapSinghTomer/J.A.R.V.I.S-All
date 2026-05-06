import asyncio
import os
import httpx
from dotenv import load_dotenv


async def test_nvidia():
    load_dotenv()
    api_key = os.getenv("NVIDIA_API_KEY")
    if api_key and api_key.startswith('"'):
        api_key = api_key.strip('"')

    models = [
        "meta/llama-3.1-405b-instruct",
        "meta/llama-3.1-70b-instruct",
        "nvidia/llama-3.1-nemotron-70b-instruct",
        "nvidia/nemotron-4-340b-instruct",
    ]

    async with httpx.AsyncClient() as client:
        for model in models:
            print(f"Testing model: {model}")
            try:
                response = await client.post(
                    "https://integrate.api.nvidia.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "hi"}],
                        "max_tokens": 10,
                    },
                    timeout=30.0,
                )
                print(f"Status: {response.status_code}")
                if response.status_code != 200:
                    print(f"Response: {response.text}")
                else:
                    print("Success!")
            except Exception as e:
                print(f"Error: {e}")
            print("-" * 20)


if __name__ == "__main__":
    asyncio.run(test_nvidia())
