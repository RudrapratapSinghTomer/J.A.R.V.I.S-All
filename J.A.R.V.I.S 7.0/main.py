import asyncio
import sys
from mind import SequenceArchitect
from loguru import logger
from dotenv import load_dotenv


async def input_loop(mind: SequenceArchitect):
    print("\n--- J.A.R.V.I.S 7.0 SEQUENCE MEMORY ACTIVE ---")
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
    load_dotenv()
    mind = SequenceArchitect()
    tasks = [asyncio.create_task(mind.loop()), asyncio.create_task(input_loop(mind))]
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.warning("Manually terminated.")
    finally:
        for t in tasks:
            t.cancel()
        logger.info("J.A.R.V.I.S 7.0 Offline.")


if __name__ == "__main__":
    asyncio.run(main())
