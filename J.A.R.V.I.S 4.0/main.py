import asyncio
from mind import AutonomousArchitect
from loguru import logger
from dotenv import load_dotenv


async def main():
    """Ignite J.A.R.V.I.S 4.0: Autonomous Architect."""
    load_dotenv()

    # Initialize the Sovereign Architect
    # All configuration (API keys, models) is loaded directly from .env in the constructor
    mind = AutonomousArchitect()

    logger.success("Initializing J.A.R.V.I.S 4.0: Sovereign Architect...")

    try:
        # Start the Cognitive Loop
        await mind.loop()
    except asyncio.CancelledError:
        logger.info("Mind suspension requested by user.")
    except Exception as e:
        logger.critical(f"Critical System Failure in Mind: {e}")
    finally:
        logger.warning("J.A.R.V.I.S 4.0 Mind Offline.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("System manually terminated.")
