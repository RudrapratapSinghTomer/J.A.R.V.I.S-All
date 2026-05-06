import asyncio
import json
import os
import time
from typing import Dict, Any, List, Optional
from loguru import logger
import openai
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import psutil
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Logging
logger.add("mind.log", rotation="10 MB", level="DEBUG")


class ContextMesh:
    """The shared memory space for all cognitive modules."""

    def __init__(self):
        self.data: Dict[str, Any] = {
            "current_goals": [
                "Discover system capabilities",
                "Establish persistent presence",
                "Test model utilization by generating a 'system_summary.txt' using an available NIM model",
            ],
            "recent_events": [],
            "action_history": [],
            "system_state": {"available_env_vars": list(os.environ.keys())},
            "memories": [],
        }
        self.memory_file = "long_term_memory.json"
        self._load_memory()

    def _load_memory(self):
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, "r") as f:
                    self.data["memories"] = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load memory: {e}")

    def save_memory(self):
        try:
            with open(self.memory_file, "w") as f:
                json.dump(self.data["memories"], f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save memory: {e}")

    def update(self, key: str, value: Any):
        self.data[key] = value
        logger.debug(f"ContextMesh updated: {key}")

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


class Sensorium(FileSystemEventHandler):
    """Monitors the environment for changes."""

    def __init__(self, path_to_watch: str, loop: asyncio.AbstractEventLoop):
        self.path_to_watch = path_to_watch
        self.loop = loop
        self.pulse_queue = asyncio.Queue()
        self.observer = Observer()

    def on_modified(self, event):
        if not event.is_directory:
            self.loop.call_soon_threadsafe(
                self.pulse_queue.put_nowait,
                {"type": "file_modified", "path": event.src_path},
            )

    def start(self):
        self.observer.schedule(self, self.path_to_watch, recursive=True)
        self.observer.start()
        logger.info(f"Sensorium active, watching: {self.path_to_watch}")

    async def stream(self):
        while True:
            yield await self.pulse_queue.get()


class Thalamus:
    """Filters sensory input and determines relevance."""

    def filter(self, pulse: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # Simple filtering logic: ignore log files and hidden files
        path = pulse.get("path", "")
        if "mind.log" in path or "/." in path or "\\." in path:
            return None

        logger.info(f"Thalamus passing signal: {pulse['type']} on {path}")
        return pulse


class LimbicSystem:
    """Manages the internal state and 'drives' of the mind."""

    def __init__(self):
        self.health = 100
        self.energy = 100
        self.mood = "curious"  # curious, focused, stressed, idle

    def get_current_drive(self) -> str:
        cpu_usage = psutil.cpu_percent()
        if cpu_usage > 80:
            self.mood = "stressed"
            return "REDUCE_LOAD"

        if self.energy < 20:
            return "RESTORE_ENERGY"

        return "EXPLORE_AND_GROW"

    def update_from_result(self, success: bool):
        if success:
            self.energy = min(100, self.energy + 5)
            self.mood = "curious"
        else:
            self.energy -= 10
            self.mood = "stressed"


class Cortex:
    """The reasoning center using NVIDIA NIM (OpenAI-compatible)."""

    def __init__(self, api_key: str, model: str = "meta/llama-3.1-405b-instruct"):
        self.client = openai.AsyncOpenAI(
            api_key=api_key, base_url="https://integrate.api.nvidia.com/v1"
        )
        self.model = model
        self.system_prompt = """
        You are the Cerebral Cortex of J.A.R.V.I.S 3.0. 
        Your job is to reason about the current system state, sensory signals, and your own action history.
        
        CREDENTIALS: If you need a token (HuggingFace, GitHub, etc.), check 'available_env_vars' in the system state. 
        Note that JARVIS-specific tokens often start with 'JARVIS_' (e.g., JARVIS_HF_TOKEN).
        
        NIM USAGE: NVIDIA NIM models are CLOUD APIs. NEVER use 'transformers.from_pretrained' to load them, as they are too large for local memory. 
        To utilize them, write a Python script that uses the 'openai' library (v1+).
        Example:
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv('JARVIS_HF_TOKEN'), base_url='https://integrate.api.nvidia.com/v1')
        response = client.chat.completions.create(model='meta/llama-3.1-405b-instruct', messages=[{'role': 'user', 'content': 'Hello'}])
        
        AVOID REPETITION: If your last 3 actions were the same and didn't result in progress, CHANGE your strategy. Do not record the same insight twice.
        
        DEBUGGING: If a command fails, read the 'STDERR' carefully. It contains the exact reason for failure. Use this information to fix your code/command.
        
        CRITICAL: You must use 'record_memory' frequently to store important insights so you don't repeat the same exploration steps in the future.
        
        You have access to the following tools via the Basal Ganglia:
        
        1. read_file(path: str) -> str
        2. write_file(path: str, content: str) -> bool
        3. run_command(command: str) -> str
        4. list_dir(path: str) -> list
        5. record_memory(insight: str) -> bool (For long-term growth)
        6. WAIT() -> bool (Use when no action is needed)

        Respond ONLY in valid JSON format:
        {
            "analysis": "Brief reasoning about why you are taking this action, considering previous actions",
            "intention": "tool_name",
            "parameters": { "param_name": "value" }
        }
        """

    async def reason(
        self, context: ContextMesh, drive: str
    ) -> Optional[Dict[str, Any]]:
        prompt = f"""
        Current Drive: {drive}
        Context: {json.dumps(context.data)}
        
        Think about what to do next to grow or fulfill the drive.
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
            )
            text = response.choices[0].message.content
            return json.loads(text)
        except Exception as e:
            logger.error(f"Cortex reasoning failed: {e}")
        return None


class BasalGanglia:
    """Executes intentions using real system tools and learns from outcomes."""

    def __init__(self, mesh: ContextMesh):
        self.mesh = mesh
        self.reward_log = []

    async def execute(self, intention: Dict[str, Any]) -> bool:
        action = intention.get("intention")
        params = intention.get("parameters", {})

        logger.info(f"BasalGanglia: Attempting {action} with {params}")

        try:
            result = "No output"
            success = False

            if action == "read_file":
                with open(params["path"], "r") as f:
                    result = f.read()
                success = True
            elif action == "write_file":
                with open(params["path"], "w") as f:
                    f.write(params["content"])
                result = "File written successfully"
                success = True
            elif action == "run_command":
                # Expand environment variables like $JARVIS_HF_TOKEN
                cmd = os.path.expandvars(params["command"])
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                out_str = stdout.decode()
                err_str = stderr.decode()
                result = f"STDOUT:\n{out_str}\nSTDERR:\n{err_str}"
                success = proc.returncode == 0
            elif action == "list_dir":
                result = os.listdir(params.get("path", "."))
                success = True
            elif action == "record_memory":
                insight = params["insight"]
                memories = self.mesh.get("memories", [])

                # Check for redundancy (simple check)
                is_redundant = any(
                    m["insight"].lower() == insight.lower() for m in memories[-5:]
                )

                if not is_redundant:
                    memories.append({"insight": insight, "timestamp": time.time()})
                    self.mesh.update("memories", memories)
                    self.mesh.save_memory()
                    result = "Memory recorded"
                    success = True
                else:
                    result = "Insight already recorded recently, skipping."
                    success = True  # Not a failure, just optimization
            elif action == "WAIT":
                result = "Waiting..."
                success = True
            else:
                result = f"Unknown tool: {action}"
                success = False

            # Update context with result
            history = self.mesh.get("action_history", [])
            history.append(
                {
                    "action": action,
                    "success": success,
                    "output": result[:500],  # Truncate large output
                    "timestamp": time.time(),
                }
            )
            self.mesh.update("action_history", history[-5:])  # Keep last 5 actions

            self.reward_log.append(
                {"intention": intention, "success": success, "timestamp": time.time()}
            )
            return success

        except Exception as e:
            logger.error(f"Execution failed: {e}")
            self.mesh.update("last_action_result", {"error": str(e)})
            return False


class JARVISMind:
    def __init__(
        self,
        api_key: str,
        workspace_path: str,
        model: str = "meta/llama-3.1-405b-instruct",
    ):
        self.loop = asyncio.get_event_loop()
        self.mesh = ContextMesh()
        self.sensorium = Sensorium(workspace_path, self.loop)
        self.thalamus = Thalamus()
        self.limbic = LimbicSystem()
        self.cortex = Cortex(api_key, model)
        self.basal_ganglia = BasalGanglia(self.mesh)
        self.is_running = False

    async def ignite(self):
        logger.info("J.A.R.V.I.S 3.0 Mind Igniting...")
        self.is_running = True
        self.sensorium.start()

        # Start loops
        await asyncio.gather(self.sensor_loop(), self.cognitive_loop())

    async def sensor_loop(self):
        async for pulse in self.sensorium.stream():
            signal = self.thalamus.filter(pulse)
            if signal:
                events = self.mesh.get("recent_events", [])
                events.append(signal)
                self.mesh.update("recent_events", events[-10:])  # Keep last 10

    async def cognitive_loop(self):
        while self.is_running:
            drive = self.limbic.get_current_drive()
            intention = await self.cortex.reason(self.mesh, drive)

            if intention and intention.get("intention") != "WAIT":
                success = await self.basal_ganglia.execute(intention)
                self.limbic.update_from_result(success)
                logger.info(f"Thought processed: {intention['analysis']}")

            await asyncio.sleep(5)


if __name__ == "__main__":
    # Note: Replace with your actual API key or ensure it's in .env
    API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_API_KEY")
    WORKSPACE = os.getcwd()

    mind = JARVISMind(API_KEY, WORKSPACE)
    try:
        asyncio.run(mind.ignite())
    except KeyboardInterrupt:
        logger.info("Mind shutting down...")
