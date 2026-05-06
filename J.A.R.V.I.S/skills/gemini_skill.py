import os
import logging

# Migrated from deprecated google.generativeai to google.genai (new SDK)
try:
    from google import genai
    from google.genai import types as genai_types
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False

logger = logging.getLogger("jarvis.skills.gemini")

MODEL_ID = "gemini-2.0-flash" # High-speed next-gen model

class GeminiSkill:
    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY")
        self.client = None
        if not _GENAI_AVAILABLE:
            logger.warning("google-genai package not installed. Run: pip install google-genai")
            return
        if self.api_key and "your_" not in self.api_key:
            try:
                self.client = genai.Client(api_key=self.api_key)
                logger.info(f"Gemini Flash core: READY (model={MODEL_ID})")
            except Exception as e:
                logger.error(f"Gemini init failed: {e}")

    async def ask(self, prompt: str) -> str:
        """Call Gemini Flash for high-speed web/complex queries."""
        if not self.client:
            return "Sir, my Gemini core is not configured. Please provide a valid Google API key."

        try:
            full_prompt = (
                f"You are J.A.R.V.I.S., a helpful AI assistant. "
                f"Answer concisely for voice output. Question: {prompt}"
            )
            response = await self.client.aio.models.generate_content(
                model=MODEL_ID,
                contents=full_prompt,
            )
            return response.text.strip()
        except Exception as e:
            logger.error(f"Gemini call failed: {e}")
            return f"I encountered an error while reaching my satellite processing core, Sir: {e}"

# Singleton
gemini_core = GeminiSkill()
