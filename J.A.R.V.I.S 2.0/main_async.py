import sys
import io
import asyncio
import logging
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv


def setup_logging(log_dir: str = "logs"):
    """Initialize system-wide logging to both console and file."""
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_file = os.path.join(log_dir, "jarvis.log")

    # Root logger configuration
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5),
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Lower level for core and agents to get more detail
    logging.getLogger("jarvis").setLevel(logging.DEBUG)

    # Silence noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.INFO)


if sys.platform == "win32":
    # Ensure UTF-8 output for Windows terminals to support emojis
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from core import Mind
from core.api import app as api_app, set_mind
from audio.ears import Ears
from agents import AgentTask
import uvicorn

# Load environment variables early
load_dotenv()


import argparse


def build_runtime(project_root: str | Path | None = None) -> Mind:
    return Mind.default(project_root=project_root or Path.cwd())


async def run_once(message: str) -> str:
    mind = build_runtime()
    decision = await mind.handle_event(
        message, metadata={"source": "terminal", "auth_confidence": 1.0}
    )
    return decision.response


async def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(
        description="J.A.R.V.I.S. 2.0 Autonomous Assistant"
    )
    parser.add_argument("--port", type=int, default=8080, help="API Server port")
    parser.add_argument("--no-voice", action="store_true", help="Disable ears/voice")
    args = parser.parse_args()

    mind = build_runtime()
    set_mind(mind)
    ears = None

    # Start API Server with fallback
    current_port = args.port
    server_started = False
    max_retries = 3

    while not server_started and max_retries > 0:
        try:
            print(f"DEBUG: Starting API Server on http://0.0.0.0:{current_port}")
            config = uvicorn.Config(
                api_app, host="0.0.0.0", port=current_port, log_level="warning"
            )
            server = uvicorn.Server(config)
            api_task = asyncio.create_task(server.serve())
            server_started = True
        except OSError as e:
            if e.errno == 10048:
                print(
                    f"WARNING: Port {current_port} is busy. Trying {current_port + 1}..."
                )
                current_port += 1
                max_retries -= 1
            else:
                raise e

    # Wait a moment for server to bind
    await asyncio.sleep(1)

    print("DEBUG: Initializing Mind and Agents...")
    await mind.start_consciousness()

    # Trigger Staggered Boot Sequence
    if "system_agent" in mind.agents:
        print("DEBUG: Initiating staggered boot sequence...")
        await mind.agents["system_agent"].handle(
            AgentTask(content="initialize system", intents=["initialize"])
        )

    print("DEBUG: Mind consciousness and staggered initialization active.")

    # Initialize Ears
    loop = asyncio.get_running_loop()

    def ears_callback(text: str):
        # Schedule the mind event on the main event loop
        asyncio.run_coroutine_threadsafe(handle_voice_input(mind, text), loop)

    ears = Ears(on_transcription=ears_callback)
    if not args.no_voice and mind.heart.voice.enabled:
        ears.start()

    print("J.A.R.V.I.S. 2.0 online. Type /status, /identity, or /quit.")
    try:
        while True:
            message = await asyncio.to_thread(input, "you> ")
            if message.strip() in {"/quit", "quit", "exit"}:
                break
            if message.strip() == "/status":
                print(mind.self_awareness())
                continue
            if message.strip() == "/identity":
                print(mind.heart.get_context()["identity"])
                continue

            if message.strip().startswith("/voice"):
                parts = message.strip().split(maxsplit=2)
                sub = parts[1] if len(parts) > 1 else ""
                if sub == "on":
                    mind.heart.toggle_voice_mode(True)
                    ears.start()
                    print("jarvis> Voice mode enabled. Listening for 'Jarvis'...")
                elif sub == "off":
                    mind.heart.toggle_voice_mode(False)
                    ears.stop()
                    print("jarvis> Voice mode disabled.")
                elif sub == "tts":
                    enabled = mind.heart.toggle_tts()
                    print(f"jarvis> Voice TTS {'enabled' if enabled else 'disabled'}.")
                elif sub == "status":
                    v = mind.heart.voice
                    print(
                        f"jarvis> Voice: {'ON' if v.enabled else 'OFF'} | TTS: {'ON' if v.tts_enabled else 'OFF'}"
                    )
                else:
                    print("Usage: /voice [on|off|tts|status]")
                continue

            print(f"DEBUG: Input received: '{message}'")
            try:
                decision = await mind.handle_event(
                    message, metadata={"source": "terminal", "auth_confidence": 1.0}
                )
                print(f"DEBUG: Decision made: {decision.intent}")
                print(f"jarvis> {decision.response}")
            except Exception as e:
                print(f"ERROR in mind.handle_event: {e}")
                import traceback

                traceback.print_exc()
    finally:
        if ears:
            ears.stop()
        await mind.stop_consciousness()


async def handle_voice_input(mind: Mind, text: str):
    """Handle input from the Ears system."""
    print(f"\rvoice> {text}")
    try:
        decision = await mind.handle_event(
            text, metadata={"source": "voice", "auth_confidence": 0.9}
        )
        print(f"\njarvis> {decision.response}")
        print("you> ", end="", flush=True)  # Reset the prompt
    except Exception as e:
        print(f"\nERROR in voice handler: {e}")


if __name__ == "__main__":
    asyncio.run(main())
