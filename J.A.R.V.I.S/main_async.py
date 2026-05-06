import asyncio
import time
from datetime import datetime
import logging
import os
import sys
import threading
import re
import contextlib
import warnings
from pathlib import Path
from dotenv import load_dotenv

# Suppress DeprecationWarnings from external packages (like instructor/cognee)
warnings.filterwarnings("ignore", category=FutureWarning, module="instructor")
warnings.filterwarnings("ignore", category=DeprecationWarning)
load_dotenv()

# CRITICAL: Set tiktoken cache dir BEFORE any cognee/litellm import.
_TIKTOKEN_CACHE = Path(__file__).parent / "data" / "tiktoken_cache"
_TIKTOKEN_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(_TIKTOKEN_CACHE))

# Core Modules
from core.config import SpeechConfig, SystemConfig
from core.listener import JarvisInterface
from core.llm_client import brain
from core.speech_output import speaker
from core.session_manager import Session
from core.intent_router import IntentRouter
from core.mind_loop import mind_loop
from core.prompt_refiner import refiner
from integrations.hermes_submind import initialize_hermes_submind, hermes_submind

# Setup Logging
logs_dir = Path(__file__).parent / "logs"
logs_dir.mkdir(parents=True, exist_ok=True)

# --- PID LOCKFILE ---
PID_FILE = Path(__file__).parent / "jarvis.pid"

def acquire_lock():
    """Ensure only one instance of JARVIS is running."""
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text())
            # Check if process actually exists
            import psutil
            if psutil.pid_exists(old_pid):
                print(f"Sir, another instance of J.A.R.V.I.S. (PID {old_pid}) is already active. Neutralizing...")
                p = psutil.Process(old_pid)
                p.terminate()
                try:
                    p.wait(timeout=3)
                except psutil.TimeoutExpired:
                    print(f"Process {old_pid} is stubborn. Forcefully purging...")
                    p.kill()
                    p.wait(timeout=2)
        except Exception:
            pass
    PID_FILE.write_text(str(os.getpid()))

def release_lock():
    if PID_FILE.exists():
        PID_FILE.unlink()

acquire_lock()
import atexit
atexit.register(release_lock)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(logs_dir / "jarvis_async.log")
    ]
)
logger = logging.getLogger("jarvis.main")


class JarvisAsyncCore:
    STALE_HEARTBEAT_SECONDS = 45
    HEARTBEAT_INTERVAL_SECONDS = 30
    LISTENER_STALL_WARN_SECONDS = 90

    def __init__(self):
        self.workspace_root = Path(__file__).parent
        self.interface = JarvisInterface()
        self.session = Session()
        self.is_awake = False
        self.last_wake_time = 0
        self.CONVERSATION_TIMEOUT = SpeechConfig.CONVERSATION_TIMEOUT
        self.llm_ready = False
        self.host_mode = True  # Determined during startup_checks via face scan
        self.host_name = os.getenv("JARVIS_HOST_NAME", "Sir")
        self.override_pw = os.getenv("JARVIS_OVERRIDE_PASSWORD", "")
        # Router is created AFTER face scan so it gets the correct host_mode
        self.router = None
        self.mind_loop_task = None
        self.current_cmd_task = None 
        self.listening_announced = False # Prevent repetitive "Listening..."
        self._last_listener_tick = time.time()
        self._heartbeat_task = None

    @staticmethod
    def _log_task_result(task: asyncio.Task):
        """Surface background task failures instead of swallowing them."""
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Command task failed: {e}", exc_info=True)

    @staticmethod
    def _is_wake_text(text_lower: str) -> bool:
        """
        Robust wake-word detection.
        Accepts variants like:
        - jarvis
        - j.a.r.v.i.s
        - j a r v i s
        """
        if "jarvis" in text_lower:
            return True

        compact = re.sub(r"[^a-z]", "", text_lower)
        return "jarvis" in compact

    async def startup_checks(self):
        """
        Run all startup checks before entering the main loop.
        Order: Face-ID → Security → LLM Health → Memory
        """
        # 0. SILENT FACE-ID SCAN — no pop-up, no notification
        logger.info("Performing silent Face-ID scan...")
        loop = asyncio.get_running_loop()
        try:
            from core.face_module import FaceModule
            fm = FaceModule()

            def _scan():
                if fm.initialize() and fm.list_enrolled():
                    # Two-attempt retry: a single blurry frame shouldn't lock out the host
                    for attempt in range(2):
                        result = fm.verify(tolerance=0.62)
                        name = result.get("name", "unknown")
                        conf = result.get("confidence", 0)
                        logger.info(f"Face-ID attempt {attempt+1}: name='{name}' confidence={conf:.3f}")
                        if name not in ("unknown", "no_face", "no_encoding", "error"):
                            return result
                    return result  # return last attempt result
                return None

            result = await loop.run_in_executor(None, _scan)

            if result is None:
                # No faces enrolled yet — don't cripple JARVIS
                logger.warning("Face-ID: No enrolled faces found. Defaulting to Host mode. Run scripts/enroll_face.py to register.")
                self.host_mode = True
                self.session.verified_user = "unenrolled"
                self.session.last_verified_time = datetime.now()
            else:
                name = result.get("name", "unknown")
                if name not in ("unknown", "no_face", "no_encoding", "error"):
                    self.host_mode = True
                    self.session.verified_user = name
                    self.session.last_verified_time = datetime.now()
                    self.session.auth_method = "face"
                    logger.info(f"Face-ID: HOST verified — '{name}'")
                else:
                    self.host_mode = False
                    self.session.verified_user = "guest"
                    logger.info(f"Face-ID: GUEST mode — face result was '{name}'")
        except Exception as e:
            logger.warning(f"Face-ID scan failed (defaulting to Guest mode): {e}")
            self.host_mode = False
            self.session.verified_user = "error"

        # Build router now that host_mode is determined
        self.router = IntentRouter(self.interface, self.session, host_mode=self.host_mode)

        # 1. Security check — ALWAYS runs
        logger.info("Running startup security check...")
        try:
            import sys
            sys.path.insert(0, str(Path(__file__).parent))
            from scripts.security_monitor import check_security
            is_secure = check_security(speak_func=None)
            self.session.security_status = "clean" if is_secure else "warnings_found"
            if not is_secure:
                await speaker.speak("Security alert, Sir. Warnings found in the nightly scan. Please check the logs.")
            else:
                logger.info("Security check passed.")
        except Exception as e:
            logger.warning(f"Security check skipped: {e}")

        # 2. LLM health check
        logger.info("Checking local LLM cores (Claw & Ollama)...")
        try:
            health = await brain.health_check()
            if health["ok"]:
                main_core = health["main"]
                core_health = health[main_core]
                if core_health.get("ok"):
                    model_name = core_health.get("model")
                    if not model_name:
                        try:
                            model_name = brain.model
                        except Exception:
                            model_name = "unknown"
                    logger.info(f"Main Brain ({main_core}) online using {model_name}")
                    self.session.llm_model = model_name
                    self.llm_ready = True
                else:
                    logger.warning(f"Main core {main_core} has issues: {core_health.get('error')}")
                    await speaker.speak(f"Warning: Main core {main_core} is experiencing issues, Sir.")
            else:
                logger.error("All LLM cores are offline.")
                await speaker.speak("Warning: All neural cores are offline. Complex requests will not work, Sir.")
        except Exception as e:
            logger.error(f"Brain health check failed: {e}")

        # 3. Memory initialization (background thread)
        if not self.llm_ready:
            logger.warning("Memory startup skipped — local LLM is not ready.")
            return

        logger.info("Starting memory system in background...")
        self._start_memory_background()

    def _start_memory_background(self):
        """Initialize Cognee off the startup path so voice readiness cannot hang."""
        finished = threading.Event()

        def _run_memory():
            loop = None
            try:
                from memory.cognee_bridge import memory
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                async def _init():
                    try:
                        logger.info("Memory: Initializing engine...")
                        # Increased timeout for initial setup (Ollama model loading can be slow)
                        await asyncio.wait_for(memory.initialize(), timeout=180.0)
                        logger.info("Memory: Loading context files and building knowledge graph...")
                        await asyncio.wait_for(memory.load_context(), timeout=600.0)
                        logger.info("Memory system fully online.")
                    except asyncio.TimeoutError:
                        logger.warning("Memory initialization timed out (background).")
                    except Exception as e:
                        logger.warning(f"Memory background error: {e}")

                loop.run_until_complete(_init())
            except Exception as e:
                logger.error(f"Memory thread failed to start: {e}")
            finally:
                if loop is not None:
                    loop.close()
                finished.set()

        def _watch_memory():
            # Watchdog timeout increased to 10 minutes to allow for deep neural indexing
            if not finished.wait(timeout=600):
                logger.warning("Memory startup still running after 600s. Continuing in degraded mode.")

        threading.Thread(target=_run_memory, name="jarvis-memory-init", daemon=True).start()
        threading.Thread(target=_watch_memory, name="jarvis-memory-watchdog", daemon=True).start()

    async def startup(self):
        """Perform system initialization."""
        print("\n" + "="*60)
        print("   J.A.R.V.I.S — Asynchronous Neural Assistant")
        print("   Status: 100% Local · Neural Voice · Async Brain")
        print("="*60 + "\n")

        await self.startup_checks()
        
        # 0.5 Initialize Hermes Submind
        logger.info("Initializing Hermes Submind integration...")
        await initialize_hermes_submind(self)

        # 1. PLAY STARTUP ANTHEM (requested by user)
        # We start this in the background so it doesn't block the system greeting
        asyncio.create_task(self._play_anthem())

        # 2. Identity-aware greeting
        logger.info("Sending final greeting...")
        user = getattr(self.session, 'verified_user', 'unenrolled')
        if self.host_mode:
            if user == 'unenrolled':
                await speaker.speak("Systems synchronized. No host profile found. Running in unrestricted mode.")
            else:
                await speaker.speak(f"Welcome back, {self.host_name}. All systems are online. Full host access granted.")
        else:
            await speaker.speak("Hello. I am J.A.R.V.I.S. I am currently operating in guest mode with limited access.")
        logger.info("Startup complete.")

    async def _play_anthem(self):
        """Play the user's requested startup song via YouTube."""
        try:
            from skills.youtube_skill import play_video
            # New default anthem: https://youtu.be/pAgnJDJN4VA?si=ksQv5qen0BzxvpKD
            logger.info("Initiating Startup Anthem in background...")
            # Use run_in_executor because play_video is likely blocking
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, play_video, "https://youtu.be/pAgnJDJN4VA?si=ksQv5qen0BzxvpKD")
        except Exception as e:
            logger.warning(f"Failed to play startup anthem: {e}")

    async def run(self):
        """Main Async Loop with PID Lock & Singleton Protection."""
        if not self._acquire_lock():
            return

        try:
            await self.startup()
            self.mind_loop_task = asyncio.create_task(mind_loop.start())
            
            # Start the PID Heartbeat Task
            self._heartbeat_task = asyncio.create_task(self._lock_heartbeat())
            
            loop = asyncio.get_running_loop()
            STOP_WORDS = ["stop", "shut up", "be quiet", "cancel", "hold on", "never mind"]
            
            logger.info("J.A.R.V.I.S. is now listening...")
            
            while True:
                if not self.listening_announced:
                    print("\n[SYSTEM] Listening...")
                    self.listening_announced = True

                self._last_listener_tick = time.time()
                text, audio_path = await loop.run_in_executor(None, self.interface.listen)
                self._last_listener_tick = time.time()
                
                if not text:
                    continue

                text_lower = text.lower().strip()
                self.listening_announced = False
                
                if any(sw in text_lower for sw in STOP_WORDS):
                    if self.current_cmd_task and not self.current_cmd_task.done():
                        logger.info("GLOBAL STOP TRIGGERED.")
                        self.current_cmd_task.cancel()
                        speaker.stop() 
                        from skills.youtube_skill import stop_music
                        stop_music()
                        await speaker.speak("Understood. I am standing by.")
                        continue

                current_time = time.time()
                is_in_conversation = (current_time - self.last_wake_time) < self.CONVERSATION_TIMEOUT
                is_wake = self._is_wake_text(text_lower)

                if is_wake or is_in_conversation:
                    self.last_wake_time = current_time
                    logger.info(f"Processing Raw: {text_lower}")
                    
                    # 1. Refine the prompt (Neural Guard Pass)
                    refined_data = await refiner.refine(text_lower)
                    refined_text = refined_data["refined_text"]
                    intent_hint = refined_data["intent"]

                    if self.current_cmd_task and not self.current_cmd_task.done():
                        self.current_cmd_task.cancel()
                        speaker.stop()

                    self.current_cmd_task = asyncio.create_task(
                        self.router.process_command(refined_text, audio_path=audio_path, forced_intent=intent_hint)
                    )
                    self.current_cmd_task.add_done_callback(self._log_task_result)
                    # We do NOT await here, so J.A.R.V.I.S. can listen while speaking.
                    # The next iteration of the loop will handle interruptions via self.current_cmd_task.cancel()

        except asyncio.CancelledError:
            logger.info("Main loop cancelled.")
        finally:
            self._release_lock()
            mind_loop.stop()
            if self.mind_loop_task is not None:
                self.mind_loop_task.cancel()
            if self.current_cmd_task is not None:
                self.current_cmd_task.cancel()
            if self._heartbeat_task is not None:
                self._heartbeat_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._heartbeat_task
            
            # Shutdown Hermes
            if hermes_submind:
                asyncio.create_task(hermes_submind.shutdown())

    def _acquire_lock(self) -> bool:
        """Prevent multiple instances from running simultaneously."""
        lock_file = SystemConfig.LOCK_FILE
        lock_file.parent.mkdir(parents=True, exist_ok=True)

        if lock_file.exists():
            try:
                with open(lock_file, "r") as f:
                    old_pid = int(f.read().strip())
                
                # Check if the old process is still alive
                # On Windows, psutil.pid_exists can give false positives for recently dead processes
                # So we do a more thorough check
                import psutil
                process_still_alive = False
                
                if psutil.pid_exists(old_pid):
                    try:
                        # Try to get the process and verify it's actually our J.A.R.V.I.S. instance
                        p = psutil.Process(old_pid)
                        # Check if the process name matches python or if the command line contains main_async.py
                        cmdline = " ".join(p.cmdline()).lower() if p.cmdline() else ""
                        if "python" in p.name().lower() and ("main_async.py" in cmdline or "jarvis" in cmdline):
                            process_still_alive = True
                            logger.info(f"Verified J.A.R.V.I.S. instance running at PID {old_pid}")
                        else:
                            logger.warning(f"PID {old_pid} exists but is not a J.A.R.V.I.S. instance (process: {p.name()})")
                    except (psutil.NoSuchProcess, psutil.AccessDenied, Exception) as e:
                        logger.warning(f"Could not verify PID {old_pid}: {e}")
                        process_still_alive = False
                else:
                    logger.info(f"Previous PID {old_pid} is not running. Cleaning up stale lock.")
                
                if process_still_alive:
                    # [STARK-UPGRADE] Heartbeat Check: See if the existing process is actually alive/responsive
                    import time
                    last_pulse = lock_file.stat().st_mtime
                    seconds_since_pulse = time.time() - last_pulse
                    
                    if seconds_since_pulse > self.STALE_HEARTBEAT_SECONDS:
                        logger.warning(f"Detected a HUNG J.A.R.V.I.S. instance at PID {old_pid} (last pulse: {seconds_since_pulse:.1f}s ago).")
                        logger.info(f"Sir, I am attempting to autonomously terminate the unresponsive instance and reclaim the core.")
                        try:
                            p = psutil.Process(old_pid)
                            p.terminate()
                            # Give it a moment to die
                            for _ in range(5):
                                if not p.is_running(): break
                                time.sleep(1)
                            if p.is_running(): p.kill()
                            logger.info("Successfully reclaimed the system core.")
                            process_still_alive = False
                        except Exception as e:
                            logger.error(f"Reclamation failed: {e}")
                    
                    if process_still_alive:
                        logger.error(f"FATAL: J.A.R.V.I.S. is already running (PID {old_pid}) and is responsive.")
                        print(f"\n[ERROR] J.A.R.V.I.S. is already active and healthy in another terminal (PID {old_pid}).")
                        return False
                
                if not process_still_alive:
                    # Stale lock - remove it and proceed
                    logger.info(f"Removing stale lock file from dead PID {old_pid}")
                    lock_file.unlink(missing_ok=True)
                    
            except ValueError:
                # Corrupted lock file (not a valid PID)
                logger.warning("Lock file corrupted. Removing and proceeding.")
                lock_file.unlink(missing_ok=True)
            except Exception as e:
                # Any other error - log and try to proceed
                logger.warning(f"Error checking lock file: {e}. Attempting to proceed.")

        try:
            with open(lock_file, "w") as f:
                f.write(str(os.getpid()))
            logger.info(f"PID lock acquired: {os.getpid()}")
            return True
        except Exception as e:
            logger.error(f"Failed to create lock file: {e}")
            return False

    async def _lock_heartbeat(self):
        """Periodically update the lock file modification time to signal vitality."""
        while True:
            try:
                if SystemConfig.LOCK_FILE.exists():
                    SystemConfig.LOCK_FILE.touch()
                else:
                    # Re-create if missing
                    with open(SystemConfig.LOCK_FILE, "w") as f:
                        f.write(str(os.getpid()))
                # Task health visibility
                if self.mind_loop_task is None or self.mind_loop_task.done():
                    logger.warning("Heartbeat: mind loop task is not active.")
                if (time.time() - self._last_listener_tick) > self.LISTENER_STALL_WARN_SECONDS:
                    logger.warning("Heartbeat: listener loop appears stalled; core still pulsing lock.")
            except Exception:
                pass
            await asyncio.sleep(self.HEARTBEAT_INTERVAL_SECONDS)

    def _release_lock(self):
        """Remove the lock file on exit."""
        try:
            if SystemConfig.LOCK_FILE.exists():
                SystemConfig.LOCK_FILE.unlink()
                logger.info("PID lock released.")
        except Exception as e:
            logger.warning(f"Failed to release lock file: {e}")
            # Last-resort fallback: clear file contents so stale PID is not trusted.
            try:
                with open(SystemConfig.LOCK_FILE, "w", encoding="utf-8") as f:
                    f.write("")
                logger.info("Lock file content cleared as fallback.")
            except Exception:
                pass


if __name__ == "__main__":
    jarvis = JarvisAsyncCore()
    try:
        asyncio.run(jarvis.run())
    except KeyboardInterrupt:
        logger.info("Shutdown initiated by user.")
    except Exception as e:
        logger.exception(f"Unhandled exception in main: {e}")
    finally:
        try:
            session_data = jarvis.session.end()
            logger.info(
                f"Shutdown complete. Session: {session_data['duration_minutes']}min, "
                f"{session_data['commands_count']} commands."
            )
        except Exception:
            pass
