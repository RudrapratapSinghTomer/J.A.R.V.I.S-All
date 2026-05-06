from __future__ import annotations

import logging
import os
from typing import Any, Mapping

from core.llm_client import ModelCapability, require_capability
from .base import AgentResult, AgentStatus, AgentTask, BaseAgent

logger = logging.getLogger("jarvis.claw")


class ClawAgent(BaseAgent):
    """Claw-code autonomous LLM brain agent."""

    agent_id = "claw"
    body_part = "frontal_lobe"
    capabilities = (
        "reasoning",
        "planning",
        "brain",
        "claw",
        "complex_task",
    )

    @require_capability(ModelCapability.HEAVY)
    async def handle(
        self,
        task: AgentTask,
        context: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        self.status = AgentStatus.WORKING

        claw_path = os.getenv("CLAW_PATH")
        claw_model = os.getenv("CLAW_MODEL") or "llama3.2"
        openai_base = os.getenv("OPENAI_BASE_URL")

        if not claw_path or not os.path.exists(claw_path):
            self.status = AgentStatus.IDLE
            return AgentResult(
                agent_id=self.agent_id,
                handled=False,
                summary="Claw binary not found. Please check CLAW_PATH in .env.",
                confidence=0.0,
            )

        import asyncio

        # Prepare environment
        env = os.environ.copy()
        if openai_base:
            env["OPENAI_BASE_URL"] = openai_base
            # If it's local Ollama, we might need to unset API_KEY as per docs
            if "127.0.0.1" in openai_base or "localhost" in openai_base:
                env.pop("OPENAI_API_KEY", None)

        # Execute claw.exe prompt with the task content
        try:
            cmd = [
                claw_path,
                "--model",
                claw_model,
                "prompt",
                task.content,
                "--quiet",
            ]
            
            logger.info(f"Executing Claw: {' '.join(cmd)}")
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                result_text = stdout.decode().strip()
                summary = f"Claw submind processed reasoning task."
            else:
                result_text = stderr.decode().strip()
                summary = f"Claw submind failed with code {process.returncode}."
                logger.error(f"Claw error: {result_text}")

        except Exception as e:
            result_text = str(e)
            summary = f"Claw execution error: {e}"
            logger.error(summary)

        self.status = AgentStatus.IDLE
        return AgentResult(
            agent_id=self.agent_id,
            handled=("process" in locals() and process.returncode == 0),
            summary=summary,
            data={
                "result": result_text,
                "mode": "autonomous_claw",
                "model": claw_model,
            },
            confidence=0.95
            if ("process" in locals() and process.returncode == 0)
            else 0.0,
        )
