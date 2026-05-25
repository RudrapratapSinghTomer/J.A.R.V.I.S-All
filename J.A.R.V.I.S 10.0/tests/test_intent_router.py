import os
import sys
import unittest
from unittest.mock import MagicMock

# Add parent directory to path
sys.path.append(os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from core.intent_router import SemanticIntentRouter
from core.memory import AgentMemory

class TestSemanticIntentRouter(unittest.TestCase):
    def setUp(self):
        # We will test using offline fallback mode (no LLM client passed)
        self.router = SemanticIntentRouter(llm_client=None)
        
    def test_greeting_heuristics(self):
        res = self.router.route_intent("Hello Jarvis")
        self.assertEqual(res["intent"], "GENERAL_QUERY")
        self.assertIn("conversational", res["reason"].lower())

    def test_status_heuristics(self):
        res = self.router.route_intent("system check")
        self.assertEqual(res["intent"], "GENERAL_QUERY")
        self.assertIn("conversational", res["reason"].lower())

    def test_memory_store_heuristics(self):
        res = self.router.route_intent("remember my favorite theme is Cobalt Neon Blue")
        self.assertEqual(res["intent"], "MEMORY_STORE")
        self.assertEqual(res["resolved_query"], "remember my favorite theme is Cobalt Neon Blue")

    def test_direct_action_heuristics(self):
        res = self.router.route_intent("open notepad")
        self.assertEqual(res["intent"], "DIRECT_ACTION")
        
        res2 = self.router.route_intent("take a webcam snapshot")
        self.assertEqual(res2["intent"], "DIRECT_ACTION")

    def test_web_search_heuristics(self):
        res = self.router.route_intent("search DuckDuckGo for fast-whisper")
        self.assertEqual(res["intent"], "WEB_SEARCH")

    def test_complex_plan_heuristics(self):
        res = self.router.route_intent("create a python script to run verification")
        self.assertEqual(res["intent"], "COMPLEX_PLAN")

    def test_sequence_pronoun_resolution_retry(self):
        context = {
            "last_query": "create a python script to run verification",
            "last_action": "COMPLEX_PLAN_FAILED",
            "last_error": "ModuleNotFoundError",
            "active_topic": "System Operation Failure"
        }
        # Vague command "retry"
        res = self.router.route_intent("retry", workflow_context=context)
        self.assertEqual(res["resolved_query"], "create a python script to run verification")
        self.assertEqual(res["intent"], "COMPLEX_PLAN")
        self.assertIn("resolved vague query", res["reason"].lower())

    def test_sequence_pronoun_resolution_fix(self):
        context = {
            "last_query": "create a python script to run verification",
            "last_action": "STEP_1_FAILED",
            "last_error": "SyntaxError: invalid syntax",
            "active_topic": "System Execution Error"
        }
        # Vague command "fix the error"
        res = self.router.route_intent("fix the error", workflow_context=context)
        self.assertEqual(res["resolved_query"], "Fix the error 'SyntaxError: invalid syntax' in: create a python script to run verification")
        self.assertEqual(res["intent"], "COMPLEX_PLAN")
        self.assertIn("last error", res["reason"].lower())

if __name__ == "__main__":
    unittest.main()
