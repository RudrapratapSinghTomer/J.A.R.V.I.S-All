import os
import asyncio
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

async def test_gemini():
    api_key = os.getenv("GOOGLE_API_KEY")
    print(f"DEBUG: API Key: '{api_key[:10]}...'")
    
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not found.")
        return

    try:
        genai.configure(api_key=api_key)
        model_name = os.getenv("JARVIS_GEMINI_MODEL", "gemini-1.5-flash")
        print(f"DEBUG: Model: '{model_name}'")
        model = genai.GenerativeModel(model_name)
        response = await model.generate_content_async("Hello")
        print(f"DEBUG: Success: {response.text}")
    except Exception as e:
        print(f"DEBUG: Error: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test_gemini())
