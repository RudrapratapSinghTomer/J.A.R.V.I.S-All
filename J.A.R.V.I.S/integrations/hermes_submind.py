"""
Hermes Submind Integration
===========================

Hermes acts as a specialized autonomous sub-mind that J.A.R.V.I.S can invoke
whenever it decides — with or without user commands.

J.A.R.V.I.S remains the primary orchestrator and decision-maker.
Hermes executes complex tasks, learns autonomously, creates skills.
Results feed back into J.A.R.V.I.S's memory system.

Key Features:
- JARVIS decides WHEN and WHAT to delegate (complete autonomy)
- Hermes executes tasks, learns, creates skills
- Bidirectional skill/memory synchronization
- Works seamlessly with JARVIS's async architecture
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple, Callable
from dataclasses import dataclass, asdict

logger = logging.getLogger("jarvis.hermes_submind")


@dataclass
class HermesTaskRequest:
    """Structured request to delegate to Hermes."""
    task_id: str
    description: str
    toolsets: List[str]  # e.g., ["terminal", "file", "web", "browser"]
    context: Dict[str, Any]  # Project context, user prefs, etc.
    priority: str = "normal"  # "low", "normal", "high", "critical"
    timeout_seconds: int = 300
    enable_skill_creation: bool = True
    callback_data: Optional[Dict[str, Any]] = None


@dataclass
class HermesTaskResult:
    """Result returned from Hermes execution."""
    task_id: str
    status: str  # "success", "failure", "partial", "timeout"
    result_text: str
    artifacts: Dict[str, Any]  # Generated files, logs, etc.
    new_skills_created: List[str]  # Skills learned during task
    reasoning: str
    execution_time_seconds: float
    error_message: Optional[str] = None
    learning_data: Optional[Dict[str, Any]] = None  # For JARVIS to absorb


class HermesSubmind:
    """
    The Hermes Submind Controller.
    
    JARVIS uses this to:
    1. Delegate complex multi-step tasks to Hermes (autonomously)
    2. Monitor Hermes's learning and skill creation
    3. Absorb newly created skills into JARVIS memory
    4. Make autonomous decisions about when/what to delegate
    """

    def __init__(self, jarvis_context):
        """
        Args:
            jarvis_context: Reference to the main J.A.R.V.I.S system
                           (provides access to memory, speaker, logger, etc.)
        """
        self.jarvis = jarvis_context
        self.hermes_ready = False
        self.task_queue = asyncio.Queue()
        self.pending_tasks: List[HermesTaskRequest] = []
        self.task_history: Dict[str, HermesTaskResult] = {}
        self.hermes_home = Path(os.getenv("HERMES_HOME", "./data/hermes"))
        self.hermes_skills_dir = self.hermes_home / "skills"
        self.last_sync_time = 0
        self.sync_interval = int(os.getenv("JARVIS_HERMES_SYNC_INTERVAL", "300"))  # 5 min
        self.worker_task = None
        self.is_running = False
        self.persistence_file = self.hermes_home / "task_queue.json"
        
    async def initialize(self) -> bool:
        """Initialize Hermes and start the worker."""
        logger.info("Initializing Hermes Submind...")
        
        try:
            # Ensure Hermes home directory exists
            self.hermes_home.mkdir(parents=True, exist_ok=True)
            self.hermes_skills_dir.mkdir(parents=True, exist_ok=True)
            
            # Load persistent tasks
            await self.load_queue()
            
            # Try to import Hermes
            try:
                # Add submodule path to sys.path if it exists
                hermes_submodule = self.jarvis.workspace_root / "submodules" / "hermes-agent"
                if hermes_submodule.exists():
                    # Use insert(0) to prevent shadowing by JARVIS's own 'tools' package
                    sys.path.insert(0, str(hermes_submodule))
                    logger.info(f"Priority registered Hermes submodule: {hermes_submodule}")

                # We assume 'run_agent' and 'hermes_cli' are available in the path or installed
                from run_agent import AIAgent
                logger.info("Hermes Agent successfully imported.")
            except ImportError as e:
                logger.warning(f"Hermes Agent not found (Error: {e}). Submind functionality will be limited.")
                # We don't return False here so that J.A.R.V.I.S can still run without Hermes
                # BUT the user wants it fixed, so we've cloned the submodule above.
                return False
            
            self.hermes_ready = True
            self.is_running = True
            
            # Start the background task worker
            self.worker_task = asyncio.create_task(self._task_worker())
            logger.info("Hermes task worker started.")
            
            # Start periodic skill synchronization
            asyncio.create_task(self._periodic_skill_sync())
            logger.info("Hermes skill sync scheduled.")
            
            logger.info("\u2713 Hermes Submind initialized successfully.")
            return True
            
        except Exception as e:
            logger.error(f"Hermes Submind initialization failed: {e}")
            return False

    async def call_hermes(
        self,
        description: str,
        toolsets: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
        priority: str = "normal",
        timeout_seconds: int = 300,
        enable_skill_creation: bool = True,
    ) -> HermesTaskResult:
        """
        BLOCKING call to delegate a task to Hermes.
        JARVIS awaits the result immediately.
        """
        if not self.hermes_ready:
            return HermesTaskResult(
                task_id=task_id or "unknown",
                status="failure",
                result_text="Hermes Submind is not initialized.",
                artifacts={},
                new_skills_created=[],
                reasoning="Hermes startup failed.",
                execution_time_seconds=0,
                error_message="Hermes not ready"
            )
        
        if task_id is None:
            task_id = f"hermes_{datetime.now().timestamp()}"
        
        if context is None:
            context = await self._build_default_context()
        
        if toolsets is None:
            toolsets = ["terminal", "file", "web", "browser", "huggingface", "git"]
        
        request = HermesTaskRequest(
            task_id=task_id,
            description=description,
            toolsets=toolsets,
            context=context,
            priority=priority,
            timeout_seconds=timeout_seconds,
            enable_skill_creation=enable_skill_creation,
        )
        
        logger.info(f"[JARVIS\u2192HERMES] Delegating: {task_id} - {description[:60]}...")
        result = await self._execute_hermes_task(request)
        self.task_history[task_id] = result
        
        if result.learning_data:
            await self._absorb_learnings(result)
        
        return result

    async def queue_hermes_task(
        self,
        description: str,
        toolsets: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
        priority: str = "normal",
        on_complete_callback: Optional[Callable] = None,
    ) -> str:
        """NON-BLOCKING queue of a task to Hermes."""
        if task_id is None:
            task_id = f"hermes_async_{datetime.now().timestamp()}"
        
        if context is None:
            context = await self._build_default_context()
        
        if toolsets is None:
            toolsets = ["terminal", "file", "web", "browser", "huggingface", "git"]
        
        request = HermesTaskRequest(
            task_id=task_id,
            description=description,
            toolsets=toolsets,
            context=context,
            priority=priority,
            enable_skill_creation=True,
        )
        
        request.callback_data = {
            "callback": on_complete_callback,
            "queued_at": datetime.now().isoformat(),
        }
        
        await self.task_queue.put(request)
        self.pending_tasks.append(request)
        await self.save_queue()
        logger.info(f"[JARVIS\u2192HERMES] Queued async task: {task_id}")
        return task_id

    async def save_queue(self):
        """Persist the task queue to disk."""
        try:
            data = [asdict(r) for r in self.pending_tasks]
            # Remove callback_data from serialization as it's not serializable
            for item in data:
                item.pop("callback_data", None)
            
            self.persistence_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logger.debug(f"Saved {len(self.pending_tasks)} pending tasks to disk.")
        except Exception as e:
            logger.error(f"Failed to save Hermes queue: {e}")

    async def load_queue(self):
        """Load persistent tasks from disk."""
        if not self.persistence_file.exists():
            return
        try:
            content = self.persistence_file.read_text(encoding="utf-8")
            if not content.strip(): return
            data = json.loads(content)
            for item in data:
                request = HermesTaskRequest(**item)
                await self.task_queue.put(request)
                self.pending_tasks.append(request)
            logger.info(f"Loaded {len(self.pending_tasks)} pending tasks from disk.")
        except Exception as e:
            logger.error(f"Failed to load Hermes queue: {e}")

    async def _execute_hermes_task(self, request: HermesTaskRequest) -> HermesTaskResult:
        start_time = datetime.now()
        try:
            from tools.skill_usage import list_agent_created_skill_names
            skills_before = set()
            try:
                skills_before = set(list_agent_created_skill_names())
            except: pass
            
            system_prefix = self._build_system_prefix(request.context)
            
            result_text = await asyncio.wait_for(
                self._run_hermes_oneshot(
                    prompt=request.description,
                    system_prefix=system_prefix,
                    toolsets=request.toolsets,
                    enable_skill_creation=request.enable_skill_creation,
                ),
                timeout=request.timeout_seconds
            )
            
            skills_after = set()
            try:
                skills_after = set(list_agent_created_skill_names())
            except: pass
            
            new_skills = skills_after - skills_before
            execution_time = (datetime.now() - start_time).total_seconds()
            
            return HermesTaskResult(
                task_id=request.task_id,
                status="success",
                result_text=result_text or "",
                artifacts={
                    "hermes_home": str(self.hermes_home),
                    "task_duration": execution_time,
                },
                new_skills_created=list(new_skills),
                reasoning="Task executed successfully by Hermes submind.",
                execution_time_seconds=execution_time,
                learning_data={
                    "new_skills": list(new_skills),
                    "task_description": request.description,
                    "toolsets_used": request.toolsets,
                }
            )
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            return HermesTaskResult(
                task_id=request.task_id,
                status="failure",
                result_text="",
                artifacts={},
                new_skills_created=[],
                reasoning=str(e),
                execution_time_seconds=execution_time,
                error_message=str(e)
            )

    async def _run_hermes_oneshot(self, prompt: str, system_prefix: str, toolsets: List[str], enable_skill_creation: bool) -> str:
        os.environ["HERMES_ENABLED_TOOLSETS"] = ",".join(toolsets)
        if enable_skill_creation:
            os.environ["HERMES_SKILL_CREATION_ENABLED"] = "1"
        
        loop = asyncio.get_running_loop()
        combined_prompt = f"{system_prefix}\n\nTask:\n{prompt}"
        
        # Force local Ollama for background tasks to ensure 100% availability/stability
        # unless explicitly overridden.
        if not os.getenv("HERMES_INFERENCE_PROVIDER"):
            os.environ["HERMES_INFERENCE_PROVIDER"] = "ollama"
        # Enable J.A.R.V.I.S. "Unleashed" mode: 
        # 1. Broad tool access via toolsets above.
        # 2. YOLO mode enabled for autonomous execution.
        # 3. Dynamic 'No-Delete' policy is active (enforced in approval.py).
        os.environ["HERMES_YOLO_MODE"] = "1"
        os.environ["JARVIS_RESTRICT_DELETE"] = "1"

        return await loop.run_in_executor(None, lambda: self._sync_hermes_oneshot(combined_prompt))

    def _sync_hermes_oneshot(self, prompt: str) -> str:
        try:
            from hermes_cli.oneshot import _run_agent
            return _run_agent(prompt=prompt, use_config_toolsets=True) or ""
        except Exception as e:
            logger.error(f"Sync Hermes execution failed: {e}")
            raise

    async def _task_worker(self):
        # Create a dedicated logger for the background worker
        worker_logger = logging.getLogger("jarvis.hermes_worker")
        fh = logging.FileHandler("logs/hermes_worker.log")
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        worker_logger.addHandler(fh)
        worker_logger.setLevel(logging.INFO)

        worker_logger.info("Hermes background worker started.")

        while self.is_running:
            request = None
            try:
                request = await self.task_queue.get()
                worker_logger.info(f"Processing task: {request.task_id} - {request.description[:50]}...")
                
                result = await self._execute_hermes_task(request)
                self.task_history[request.task_id] = result
                
                if result.learning_data:
                    worker_logger.info(f"Absorbing learnings from {request.task_id}")
                    await self._absorb_learnings(result)
                
                if request.callback_data and request.callback_data.get("callback"):
                    callback = request.callback_data["callback"]
                    await callback(result)
                
                worker_logger.info(f"Successfully completed task: {request.task_id}")
            except asyncio.TimeoutError:
                worker_logger.error(f"Task {request.task_id if request else 'unknown'} timed out.")
            except Exception as e:
                worker_logger.error(f"Task worker error during {request.task_id if request else 'unknown'}: {e}")
                await asyncio.sleep(5)
            finally:
                if request:
                    # Always remove from pending and save state to avoid loops
                    self.pending_tasks = [t for t in self.pending_tasks if t.task_id != request.task_id]
                    await self.save_queue()
                    self.task_queue.task_done()
                    worker_logger.info(f"Queue state synced for {request.task_id}")

    async def _absorb_learnings(self, result: HermesTaskResult):
        try:
            from memory.cognee_bridge import memory
            for skill_name in result.new_skills_created:
                skill_path = self.hermes_skills_dir / skill_name / "SKILL.md"
                if skill_path.exists():
                    skill_content = skill_path.read_text(encoding="utf-8", errors="ignore")
                    await memory.remember(
                        f"Hermes learned skill: {skill_name}\n"
                        f"Task context: {result.learning_data.get('task_description', '')}\n"
                        f"Skill excerpt:\n{skill_content[:1200]}",
                        metadata={"type": "hermes_skill", "name": skill_name, "source": "hermes_submind"},
                    )
            
            await memory.record_reflection(
                f"Hermes Task: {result.task_id}",
                f"Status: {result.status}, Skills: {len(result.new_skills_created)}",
                f"{result.learning_data.get('task_description', 'Unknown')}"
            )
        except Exception as e:
            logger.error(f"Failed to absorb learnings: {e}")

    async def _periodic_skill_sync(self):
        while self.is_running:
            await asyncio.sleep(self.sync_interval)
            if self.hermes_skills_dir.exists():
                try:
                    from tools.skill_usage import list_agent_created_skill_names
                    for skill_name in list_agent_created_skill_names():
                        await self._absorb_learnings(HermesTaskResult(
                            task_id="sync", status="success", result_text="", artifacts={},
                            new_skills_created=[skill_name], reasoning="Sync", execution_time_seconds=0,
                            learning_data={"new_skills": [skill_name], "task_description": "Sync"}
                        ))
                except: pass

    async def _build_default_context(self) -> Dict[str, Any]:
        import platform
        return {
            "timestamp": datetime.now().isoformat(),
            "platform": platform.system(),
            "os_release": platform.release(),
            "host_name": self.jarvis.host_name,
            "desktop_path": str(Path.home() / "Desktop")
        }

    def _build_system_prefix(self, context: Dict[str, Any]) -> str:
        return f"""You are Hermes Agent, an autonomous submind within J.A.R.V.I.S.
Role: Execute tasks, create skills, and report back to the main mind.
Current Environment: {context.get('platform', 'Unknown')} ({context.get('os_release', '')})
User: {context.get('host_name', 'Sir')}
System Paths: Desktop is at {context.get('desktop_path', 'N/A')}

CRITICAL: Always use the correct path syntax for the detected OS.
Context: {json.dumps(context)}"""

    async def shutdown(self):
        self.is_running = False
        if self.worker_task: self.worker_task.cancel()

# Global instance
hermes_submind: Optional[HermesSubmind] = None

async def initialize_hermes_submind(jarvis_context) -> bool:
    global hermes_submind
    hermes_submind = HermesSubmind(jarvis_context)
    return await hermes_submind.initialize()
