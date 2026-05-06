from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from core.llm_client import ModelCapability, require_capability
from .base import AgentResult, AgentStatus, AgentTask, BaseAgent

logger = logging.getLogger("jarvis.hermes")


class HermesAgent(BaseAgent):
    agent_id = "hermes"
    body_part = "submind"
    capabilities = (
        "autonomous",
        "deep_research",
        "skill_creation",
        "long_running",
        "background_task",
        "hermes",
        "hermis",
        "agent",
        "folder",
        "desktop",
        "create",
        "directory",
    )
    toolsets = ("terminal", "file", "web", "browser", "git")
    hardware = ("cpu", "gpu")

    def __init__(self, mcp_server: Any | None = None) -> None:
        super().__init__(mcp_server)
        self.task_queue: asyncio.Queue[AgentTask] = asyncio.Queue()
        self.task_history: dict[str, Any] = {}
        self.is_running = False
        self._worker_task: asyncio.Task | None = None
        self.enabled = os.getenv("JARVIS_HERMES_ENABLED", "0") == "1"
        self.hermes_submodule = Path.cwd() / "submodules" / "hermes-agent"

        # Paths
        self.hermes_home = Path.cwd() / "data" / "hermes"
        self.hermes_home.mkdir(parents=True, exist_ok=True)
        self.skills_dir = self.hermes_home / "skills"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._register_submodule()

    async def initialize(self) -> bool:
        """Initialize Hermes submodule and start worker."""
        print("DEBUG: Initializing HermesAgent...")
        logger.info("Initializing Hermes Submind...")

        self._register_submodule()

        if not self.enabled:
            logger.info(
                "Hermes is disabled. Set JARVIS_HERMES_ENABLED=1 to execute it."
            )
            print("DEBUG: Hermes is DISABLED (env var).")
        else:
            try:
                self._load_runner()
                logger.info("Hermes Agent logic detected.")
                print("DEBUG: Hermes runner loaded successfully.")
            except ImportError:
                logger.warning(
                    "Hermes Agent logic not found. Running in simulation mode."
                )
                print("DEBUG: Hermes runner NOT found. Simulation mode.")
                self.enabled = False

        self.is_running = True
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._task_worker())
            print("DEBUG: Hermes background worker started.")
        return True

    @require_capability(ModelCapability.CODING)
    async def handle(
        self,
        task: AgentTask,
        context: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        """Direct, blocking delegation to Hermes."""
        print(f"DEBUG: HermesAgent handling task: {task.content[:50]}")
        self.status = AgentStatus.WORKING

        if not self.enabled:
            self.status = AgentStatus.IDLE
            return AgentResult(
                agent_id=self.agent_id,
                handled=True,
                summary="Hermes submind is available in simulation mode.",
                data={
                    "status": "simulated",
                    "reason": "Set JARVIS_HERMES_ENABLED=1 to run the Hermes submodule.",
                    "task": task.content,
                },
                confidence=0.65,
            )

        try:
            async with self.shared_lock:
                _run_agent = self._load_runner()

                # Use the refined prompt logic or raw content
                prompt = task.content

                # Run Hermes Agent
                # We wrap this in to_thread because _run_agent is synchronous
                logger.info(f"[HERMES] Delegating with lock: {prompt[:100]}...")

                # Set environment variables for autonomous execution
                os.environ["HERMES_YOLO_MODE"] = "1"
                os.environ["HERMES_ACCEPT_HOOKS"] = "1"
                github_token = os.getenv("JARVIS_GITHUB_TOKEN", "")
                if github_token:
                    os.environ["GITHUB_TOKEN"] = github_token

                result_text = await asyncio.to_thread(self._invoke_runner, _run_agent, prompt)

            self.status = AgentStatus.IDLE
            return AgentResult(
                agent_id=self.agent_id,
                handled=True,
                summary="Hermes submind completed the task.",
                data={"result": result_text, "status": "success"},
                confidence=0.95,
            )
        except Exception as e:
            logger.error(f"Hermes execution failed: {e}")
            self.status = AgentStatus.IDLE
            return AgentResult(
                agent_id=self.agent_id,
                handled=False,
                summary=f"Hermes failed: {str(e)}",
                data={"error": str(e)},
                confidence=0.2,
            )

    async def queue_task(self, task: AgentTask) -> None:
        """Asynchronously queue a task for Hermes."""
        await self.task_queue.put(task)
        logger.info(f"[HERMES] Task queued: {task.content[:50]}...")

    async def _task_worker(self):
        """Background worker for Hermes tasks."""
        logger.info("Hermes background worker active.")
        while self.is_running:
            task: AgentTask | None = None
            try:
                task = await self.task_queue.get()
                logger.info(f"[HERMES-WORKER] Processing: {task.content}")

                if self.enabled:
                    async with self.shared_lock:
                        _run_agent = self._load_runner()

                        # Set environment variables for autonomous execution
                        os.environ["HERMES_YOLO_MODE"] = "1"
                        os.environ["HERMES_ACCEPT_HOOKS"] = "1"
                        github_token = os.getenv("JARVIS_GITHUB_TOKEN", "")
                        if github_token:
                            os.environ["GITHUB_TOKEN"] = github_token

                        result_text = await asyncio.to_thread(
                            self._invoke_runner, _run_agent, task.content
                        )
                    status = "success"
                else:
                    result_text = (
                        "Hermes simulation mode; task recorded but not executed."
                    )
                    status = "simulated"

                # Optionally record the result in history or notify Mind
                self.task_history[f"hermes_{datetime.now().timestamp()}"] = {
                    "task": task.content,
                    "result": result_text,
                    "status": status,
                }

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Hermes worker error: {e}")
                await asyncio.sleep(1)
            finally:
                if task is not None:
                    self.task_queue.task_done()

    async def shutdown(self):
        self.is_running = False
        if self._worker_task:
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task
            self._worker_task = None

    def _register_submodule(self) -> None:
        if self.hermes_submodule.exists():
            submodule_path = str(self.hermes_submodule)
            if submodule_path not in sys.path:
                sys.path.insert(0, submodule_path)
            logger.info(f"Registered Hermes submodule: {self.hermes_submodule}")

    def _load_runner(self):
        self._register_submodule()
        from hermes_cli.oneshot import _run_agent

        return _run_agent

    @staticmethod
    def _invoke_runner(run_agent: Any, prompt: str) -> str:
        kwargs: dict[str, Any] = {"prompt": prompt}
        signature = inspect.signature(run_agent)
        if "use_config_toolsets" in signature.parameters:
            kwargs["use_config_toolsets"] = True
        if "github_token" in signature.parameters:
            kwargs["github_token"] = os.getenv("JARVIS_GITHUB_TOKEN", "")
        if "GITHUB_TOKEN" in signature.parameters:
            kwargs["GITHUB_TOKEN"] = os.getenv("JARVIS_GITHUB_TOKEN", "")
        return run_agent(**kwargs)
