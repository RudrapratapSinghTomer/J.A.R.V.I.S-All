import os
import asyncio
import openai
from dotenv import load_dotenv


async def test_nim():
    load_dotenv()
    api_key = os.getenv("NVIDIA_API_KEY") or os.getenv("GEMINI_API_KEY")
    client = openai.AsyncOpenAI(
        api_key=api_key, base_url="https://integrate.api.nvidia.com/v1"
    )

    print("Testing NIM API (8b model)...")
    try:
        response = await asyncio.wait_for(
            client.chat.completions.create(
                model="meta/llama-3.1-8b-instruct",
                messages=[
                    {
                        "role": "user",
                        "content": "Hello, are you there? Respond with only 'YES'.",
                    }
                ],
                max_tokens=10,
            ),
            timeout=10,
        )
        print(f"Response: {response.choices[0].message.content}")
    except Exception as e:
        import traceback

        print(f"NIM API Failed ({type(e)}): {e}")
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_nim())
