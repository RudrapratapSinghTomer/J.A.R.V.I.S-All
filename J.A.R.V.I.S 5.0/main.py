import asyncio
import sys
from mind import SovereignConsciousness
from loguru import logger
from dotenv import load_dotenv


async def input_loop(mind: SovereignConsciousness):
    """Listens for user input and pipes it to the mind's priority queue."""
    print("\n--- J.A.R.V.I.S 5.0 CHAT ACTIVE ---")
    print("Type your message and press Enter. J.A.R.V.I.S will respond on priority.\n")

    while True:
        try:
            user_input = await asyncio.get_event_loop().run_in_executor(
                None, sys.stdin.readline
            )
            if user_input.strip():
                await mind.user_queue.put(user_input.strip())
        except Exception as e:
            logger.error(f"Input Error: {e}")


async def main():
    """Ignite J.A.R.V.I.S 5.0: Hybrid Consciousness."""
    load_dotenv()

    mind = SovereignConsciousness()

    tasks = [asyncio.create_task(mind.loop()), asyncio.create_task(input_loop(mind))]

    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.warning("System manually terminated by User.")
    except Exception as e:
        logger.critical(f"Critical System Failure: {e}")
    finally:
        for t in tasks:
            t.cancel()
        logger.info("J.A.R.V.I.S 5.0 Offline.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
