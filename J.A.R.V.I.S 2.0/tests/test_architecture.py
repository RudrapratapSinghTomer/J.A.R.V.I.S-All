from __future__ import annotations

import unittest

from agents import AgentTask, MemoryAgent
from core import Heart, LLMClient, Mind, ModelCapability
from audio import FishSpeechClient
from mcp_tools import create_default_system_mcp


class FakeMemory:
    def __init__(self) -> None:
        self.remembered: list[tuple[str, dict | None]] = []
        self.recalled: list[str] = []

    async def initialize(self) -> bool:
        return True

    async def load_context(self) -> None:
        return None

    async def remember(self, text: str, metadata: dict | None = None) -> None:
        self.remembered.append((text, metadata))

    async def recall(self, query: str) -> list[dict]:
        self.recalled.append(query)
        return [{"text": "stored item", "score": 0.5, "source": "fake"}]

    async def improve(self) -> None:
        return None


class HeartTests(unittest.TestCase):
    def test_identity_authenticates_above_threshold(self) -> None:
        heart = Heart(authentication_threshold=0.7)
        identity = heart.update_identity(face_id="owner-face", confidence=0.95)

        self.assertTrue(identity.authenticated)
        self.assertEqual(identity.face_id, "owner-face")

    def test_emotion_state_is_clamped(self) -> None:
        heart = Heart()
        emotion = heart.set_emotion("excited", intensity=2.0)

        self.assertEqual(emotion.name, "excited")
        self.assertEqual(emotion.intensity, 1.0)


class FishSpeechTests(unittest.TestCase):
    def test_emotion_tags_are_inserted(self) -> None:
        client = FishSpeechClient(enabled=False)
        prepared = client.prepare_text("Hello, sir.", emotion="excited", intensity=0.9)

        self.assertIn("[excited]", prepared)
        self.assertIn("[emphasis]", prepared)


class LLMClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_selects_vision_model(self) -> None:
        client = LLMClient()
        models = client.select_model(ModelCapability.VISION)

        # By default registry, vision models should be returned
        self.assertTrue(
            any(
                "vision" in m.model_id.lower() or m.capability == ModelCapability.VISION
                for m in models
            )
        )

    async def test_custom_provider_is_called(self) -> None:
        client = LLMClient()

        async def provider(request):
            return f"handled:{request.capability.name}:{request.purpose}"

        client.register_provider("test_provider", provider)
        # Manually inject a model that uses this provider
        from core.llm_client import ModelProfile

        client.registry.append(
            ModelProfile(
                model_id="test-model",
                provider="test_provider",
                capability=ModelCapability.HEAVY,
            )
        )

        response = await client.generate(
            "deep task",
            capability=ModelCapability.HEAVY,
            purpose="deep_analysis",
        )

        self.assertEqual(response.text, "handled:HEAVY:deep_analysis")


class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_scope_denial(self) -> None:
        server = create_default_system_mcp()
        result = await server.call_tool(
            "system.metrics",
            {},
            agent_id="test",
            scope="system:write",
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "scope_denied")


class MemoryAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_remember_request_stores_instead_of_recalls(self) -> None:
        fake_memory = FakeMemory()
        agent = MemoryAgent(memory_backend=fake_memory)

        result = await agent.handle(
            AgentTask("remember my GPU profile", intent="memory")
        )

        self.assertTrue(result.handled)
        self.assertEqual(result.data["action"], "remembered")
        self.assertEqual(len(fake_memory.remembered), 1)
        self.assertEqual(fake_memory.recalled, [])


class MindTests(unittest.IsolatedAsyncioTestCase):
    async def test_mind_delegates_complex_code_error_to_agents(self) -> None:
        mind = Mind.default()
        decision = await mind.handle_event("Analyze this error and fix the code")

        self.assertEqual(decision.intent, "monitoring")
        self.assertIn("monitoring", decision.agents)
        self.assertIn("coding", decision.agents)
        self.assertIn("memory", decision.agents)

    async def test_conversation_uses_llm_when_no_agent_matches(self) -> None:
        mind = Mind.default()
        decision = await mind.handle_event("How are you today?")

        self.assertEqual(decision.intent, "conversation")
        self.assertEqual(decision.agents, [])
        self.assertIsNotNone(decision.llm)

    async def test_voice_request_uses_voice_agent(self) -> None:
        mind = Mind.default()
        decision = await mind.handle_event(
            "Speak this with emotion",
            metadata={"speech_text": "Systems are online.", "emotion": "excited"},
        )

        self.assertEqual(decision.intent, "voice")
        self.assertIn("voice", decision.agents)
        self.assertIn("[excited]", decision.results[0].data["prepared_text"])

    async def test_hermes_request_uses_hermes_intent_without_execution_by_default(
        self,
    ) -> None:
        mind = Mind.default()
        decision = await mind.handle_event("hermes deep_research this later")

        self.assertEqual(decision.intent, "hermes")
        self.assertIn("hermes", decision.agents)
        self.assertEqual(decision.results[0].data["status"], "simulated")

    async def test_consciousness_start_stop_initializes_optional_agents(self) -> None:
        mind = Mind.default()

        await mind.start_consciousness()
        await mind.stop_consciousness()

        self.assertIsNone(mind._consciousness_task)


if __name__ == "__main__":
    unittest.main()
