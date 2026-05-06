import asyncio
import logging
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from core import Mind
from agents.base import AgentTask

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jarvis.test")


async def test_full_cycle():
    logger.info("Initializing J.A.R.V.I.S. 2.0 Mind...")
    mind = Mind.default()
    await mind.start_consciousness()

    # Enable TTS for testing the mouth trigger
    mind.heart.toggle_tts(True)

    test_message = (
        "Jarvis, check my hardware security and remember that everything is fine."
    )

    logger.info(f"Sending test message: '{test_message}'")

    # 1. Handle Event
    decision = await mind.handle_event(test_message)

    logger.info("--- SYSTEM TEST RESULTS ---")
    logger.info(f"Intent(s) Detected: {decision.intent}")
    logger.info(f"Response: {decision.response}")

    # 2. Verify Background Agent Side-Effects
    # Check if Hardware was updated in Heart
    health = mind.heart.health
    logger.info(
        f"Heart Health Check: CPU={health.cpu_usage}%, Firewall={health.firewall_enabled}"
    )

    # Check if Memory was indexed
    # (In a real test, we'd query Cognee, but for now we check the Mind's internal states)

    # 3. Test Manual Evolution Hand-off
    logger.info("Testing Autonomous Learning Loop Hand-off...")
    learning_result = await mind.agents["learning_center"].handle(
        AgentTask(content="learn something", intents=["learn"])
    )

    if "evolution_plan" in learning_result.data:
        plan = learning_result.data["evolution_plan"]
        logger.info(f"LearningAgent Research: Found feature '{plan.get('feature')}'")

        # Verify the Evolution Engine is ready
        evo_result = await mind.agents["evolution_engine"].handle(
            AgentTask(content="evolve", intents=["evolve"], metadata={"plan": plan})
        )
        logger.info(f"Evolution Engine Status: {evo_result.summary}")

    await mind.stop_consciousness()
    logger.info("Integration Test Complete.")


if __name__ == "__main__":
    asyncio.run(test_full_cycle())
