import os
import asyncio
from mind import JARVISMind
from loguru import logger
from dotenv import load_dotenv


async def main():
    # Load configuration
    load_dotenv()

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error(
            "GEMINI_API_KEY not found in environment. Please set it in .env file."
        )
        return

    workspace = os.getcwd()

    model = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-405b-instruct")

    # Initialize the Mind
    mind = JARVISMind(api_key, workspace, model)

    try:
        # Ignite J.A.R.V.I.S 3.0
        await mind.ignite()
    except asyncio.CancelledError:
        logger.info("Mind suspension requested.")
    except Exception as e:
        logger.critical(f"Critical System Failure in Mind: {e}")
    finally:
        logger.info("J.A.R.V.I.S 3.0 Mind Offline.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
