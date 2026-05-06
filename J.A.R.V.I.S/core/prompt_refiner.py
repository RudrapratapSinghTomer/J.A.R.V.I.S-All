import logging
import json
from pathlib import Path
import asyncio

logger = logging.getLogger("jarvis.refiner")

class PromptRefiner:
    """
    Neural Pre-processor using Gemini 1.5 Flash.
    Cleans noisy transcriptions, identifies intent, and formats for the Main Brain.
    """
    VALID_INTENTS = {
        "GET_WEATHER", "PLAY_YOUTUBE", "GET_NEWS", "WEB_SEARCH", "SYSTEM_STATUS", 
        "TERMINAL_COMMAND", "SHUTDOWN", "ENROLL_VOICE", "IDENTIFY_ME", 
        "CODE_MODIFICATION", "DEBUG_SYSTEM", "MULTI_STEP_TASK", 
        "SYSTEM_OPTIMIZATION", "DEEP_SYNC", "MEMORY_IMPROVEMENT", "KNOWLEDGE_REQUEST"
    }

    def __init__(self):
        self.personality_path = Path(__file__).parent.parent / "context" / "personality.md"

    @property
    def instructions(self) -> str:
        """Dynamically load instructions from the personality context."""
        try:
            if self.personality_path.exists():
                return self.personality_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to load personality file: {e}")
            
        return "You are J.A.R.V.I.S., an elite AI assistant. Clean the user's input and return a JSON object."

    def _fallback(self, raw_text: str) -> dict:
        return {"refined_text": raw_text, "intent": "KNOWLEDGE_REQUEST", "confidence": 0.5}

    async def refine(self, raw_text: str) -> dict:
        """
        Scrub raw transcription and return structured intent.
        """
        if not raw_text or len(raw_text.strip()) < 3:
            return {"refined_text": raw_text, "intent": "KNOWLEDGE_REQUEST", "confidence": 1.0}

        try:
            from core.llm_client import brain
            prompt = f"{self.instructions}\n\nUser Input: \"{raw_text}\"\n\nReturn ONLY the JSON object."
            
            logger.info(f"Dispatching refinement to Main Brain ({brain.model})...")
            try:
                response_text = await asyncio.wait_for(brain.chat(prompt, enable_rag=False), timeout=15)
            except asyncio.TimeoutError:
                logger.warning("Elite Refinement timed out. Using fallback.")
                return self._fallback(raw_text)
            
            if not response_text:
                return self._fallback(raw_text)
            
            clean_json = response_text.strip()
            if "```" in clean_json:
                clean_json = clean_json.split("```")[1]
                if clean_json.startswith("json"):
                    clean_json = clean_json[4:].strip()
            
            data = json.loads(clean_json)
            refined_text = str(data.get("refined_text", raw_text)).strip() or raw_text
            intent = str(data.get("intent", "KNOWLEDGE_REQUEST")).strip().upper()
            confidence = float(data.get("confidence", 0.5))
            
            if intent not in self.VALID_INTENTS:
                intent = "KNOWLEDGE_REQUEST"
                
            return {"refined_text": refined_text, "intent": intent, "confidence": confidence}
            
        except Exception as e:
            logger.warning(f"Elite Refinement failed: {e}. Using fallback.")
            return self._fallback(raw_text)

# Singleton
refiner = PromptRefiner()
