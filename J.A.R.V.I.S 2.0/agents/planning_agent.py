from __future__ import annotations

import logging
import json
import re
import asyncio
from typing import Any, Mapping, Dict, List

from .base import AgentResult, AgentStatus, AgentTask, BaseAgent
from core.llm_client import ModelCapability, require_capability

logger = logging.getLogger("jarvis.planning")


class PlanningAgent(BaseAgent):
    """The 'Frontal Lobe' that creates plans and monitors their fulfillment."""

    agent_id = "planning_agent"
    body_part = "frontal_lobe"
    capabilities = (
        "plan",
        "architect",
        "strategy",
        "task_breakdown",
        "execute_plan",
        "monitor_goals",
    )
    toolsets = ("reasoning", "orchestration", "goal_monitoring")
    hardware = ("cloud", "gpu")

    def __init__(
        self, mcp_server: Any | None = None, llm_client: Any | None = None
    ) -> None:
        super().__init__(mcp_server)
        self.llm_client = llm_client
        self.active_goals: Dict[str, Any] = {}
        self.is_running = False
        self._loop_task: asyncio.Task | None = None
        self.interval = 45.0  # Check goals every 45 seconds

    async def initialize(self) -> bool:
        self.is_running = True
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._monitoring_loop())
        logger.info("PlanningAgent goal monitoring loop started.")
        return True

    async def shutdown(self) -> None:
        self.is_running = False
        if self._loop_task:
            self._loop_task.cancel()
        logger.info("PlanningAgent goal monitoring loop stopped.")

    @require_capability(ModelCapability.HEAVY)
    async def handle(
        self,
        task: AgentTask,
        context: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        self.status = AgentStatus.WORKING

        # 1. Check for manual push/confirmation
        if any(
            k in task.content.lower()
            for k in ("proceed", "yes", "continue", "next step", "do it")
        ):
            if self.active_goals:
                goal_id = list(self.active_goals.keys())[0]
                goal = self.active_goals[goal_id]
                await self._process_goal_step(goal_id, goal)
                return AgentResult(
                    agent_id=self.agent_id,
                    handled=True,
                    summary=f"Proceeding with mission step {goal['current_step']}.",
                    data={"goal_id": goal_id, "current_step": goal["current_step"]},
                )

        # 2. Check if we are executing/registering a plan
        if "execute_plan" in task.intents or "confirm" in task.intents:
            return await self._register_and_initiate_goal(task, context)

        # 3. Otherwise, generate a new plan
        return await self._handle_planning(task, context)

    async def _handle_planning(
        self, task: AgentTask, context: Mapping[str, Any] | None
    ) -> AgentResult:
        """Create a structured plan for the user's request."""
        context_data = context or {}
        agents_meta = context_data.get("agents_metadata", {})
        history = context_data.get("history", [])

        prompt = (
            "You are the Planning Agent (Frontal Lobe) of J.A.R.V.I.S. 2.0.\n"
            "Your goal is to take a user request and break it down into a multi-step plan.\n\n"
            "## Available Agents:\n"
            f"{json.dumps(agents_meta, indent=2)}\n\n"
            "## User Request:\n"
            f"{task.content}\n\n"
            "## Recent History:\n"
            f"{json.dumps(history, indent=2)}\n\n"
            "## Requirements for the Plan:\n"
            "1. Output a JSON list of 'steps'.\n"
            "2. For each step, include 'agent_id', 'action', 'success_criteria', and 'failure_handling'.\n"
            "3. Provide a 'summary' of the total mission.\n\n"
            "Output Format:\n"
            "Summary: [summary]\n"
            "Plan: ```json\n[JSON]\n```"
        )

        try:
            source_text = self._extract_source_plan_text(task.content)
            if source_text:
                text = source_text
            else:
                response = await self.llm_client.generate(
                    prompt, ModelCapability.HEAVY, purpose="planning"
                )
                text = response.text

            summary_match = re.search(r"Summary:\s*(.*?)(?:\nPlan:|$)", text, re.DOTALL)
            summary = (
                summary_match.group(1).strip() if summary_match else "Plan generated."
            )

            plan_match = re.search(r"```json\n(.*?)\n```", text, re.DOTALL)
            plan_steps = json.loads(plan_match.group(1)) if plan_match else []
            if not plan_steps:
                plan_steps = self._heuristic_plan_from_text(text)
                if source_text and summary == "Plan generated.":
                    summary = "Structured plan parsed from mission document."
            if not plan_steps:
                self.status = AgentStatus.IDLE
                return AgentResult(
                    agent_id=self.agent_id,
                    handled=False,
                    summary="Unable to derive executable steps from the provided plan text.",
                    data={
                        "status": "failed",
                        "plan": [],
                        "requires_confirmation": False,
                    },
                    confidence=0.2,
                )

            self.status = AgentStatus.IDLE
            return AgentResult(
                agent_id=self.agent_id,
                handled=True,
                summary=summary,
                data={
                    "plan": plan_steps,
                    "requires_confirmation": True,
                    "status": "planned",
                },
                confidence=0.95,
            )
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            return AgentResult(agent_id=self.agent_id, handled=False, summary=str(e))

    @staticmethod
    def _extract_source_plan_text(content: str) -> str | None:
        lowered = content.lower()
        markers = (
            "parse this plan:",
            "mission document:",
            "based on this mission document:",
        )
        for marker in markers:
            idx = lowered.find(marker)
            if idx >= 0:
                return content[idx + len(marker) :].strip()
        return None

    @staticmethod
    def _heuristic_plan_from_text(text: str) -> list[dict[str, Any]]:
        steps: list[dict[str, Any]] = []
        lines = [line.strip(" -\t") for line in text.splitlines() if line.strip()]

        def add(agent_id: str, action: str, criteria: str) -> None:
            steps.append(
                {
                    "agent_id": agent_id,
                    "action": action,
                    "success_criteria": criteria,
                    "failure_handling": "Report failure reason and continue with safe fallback.",
                }
            )

        if any("locate" in line.lower() or "audit" in line.lower() for line in lines):
            add(
                "coding",
                "Audit project files and identify UI/backend wiring issues in dashboard and agents.",
                "A concrete audit summary with files and actionable fixes is produced.",
            )
        if any(
            "dashboard" in line.lower()
            or "hud" in line.lower()
            or "real jarvis style" in line.lower()
            for line in lines
        ):
            add(
                "dashboard_agent",
                "Evolve dashboard UI and ensure real-time HUD/monitoring tabs remain operational.",
                "Dashboard assets are updated and status is reported as success.",
            )
        if any(
            "screen capture" in line.lower() or "dxcam" in line.lower()
            for line in lines
        ):
            add(
                "vision",
                "Validate screen-capture pathway availability and report current capture capability.",
                "Vision capability report includes availability and any fallback recommendation.",
            )
        if any(
            "failover" in line.lower() or "nvidia" in line.lower() for line in lines
        ):
            add(
                "orchestrator",
                "Audit provider failover policy and report active degraded/cooldown behavior.",
                "Failover policy status and provider health summary are reported.",
            )
        if any(
            "file structure" in line.lower() or "mind_journal" in line.lower()
            for line in lines
        ):
            add(
                "coding",
                "Write updated file structure and execution notes to mind_journal.md.",
                "mind_journal.md contains the latest execution summary.",
            )

        if not steps:
            add(
                "coding",
                "Break down the mission document into executable coding and system tasks.",
                "At least one concrete executable task is completed.",
            )
        return steps

    async def _register_and_initiate_goal(
        self, task: AgentTask, context: Mapping[str, Any] | None
    ) -> AgentResult:
        """Register the plan as an active goal for continuous monitoring."""
        plan = task.metadata.get("plan") or (context or {}).get("active_plan")
        if not plan:
            # Fallback: Check if task content contains a file path
            path_match = re.search(
                r'["\']?([a-zA-Z]:\\[^"\']+|\/[\w/\.-]+)["\']?', task.content
            )
            if path_match:
                path = path_match.group(1)
                import os

                if os.path.exists(path):
                    try:
                        with open(path, "r") as f:
                            plan_text = f.read()
                        # We need to structure this text via LLM
                        return await self._handle_planning(
                            AgentTask(
                                content=f"Create a structured multi-step plan based on this mission document: {plan_text}",
                                intents=["plan"],
                            ),
                            context,
                        )
                    except Exception as e:
                        logger.error(f"Failed to read fallback plan file: {e}")

            return AgentResult(
                agent_id=self.agent_id,
                handled=False,
                summary="No plan found to execute.",
            )

        goal_id = f"goal_{int(asyncio.get_event_loop().time())}"
        self.active_goals[goal_id] = {
            "original_request": task.content,
            "plan": plan,
            "current_step": 0,
            "results": [],
            "status": "in_progress",
            "metadata": task.metadata,
        }

        logger.info(f"Goal {goal_id} registered. Continuous monitoring active.")
        return AgentResult(
            agent_id=self.agent_id,
            handled=True,
            summary=f"Mission Initiated. I will monitor the agents and ensure all requirements are fulfilled autonomously.",
            data={"goal_id": goal_id, "status": "executing"},
            confidence=1.0,
        )

    async def _monitoring_loop(self) -> None:
        """Background loop to check goal fulfillment and push agents."""
        while self.is_running:
            await asyncio.sleep(self.interval)

            for goal_id, goal in list(self.active_goals.items()):
                if goal["status"] != "in_progress":
                    continue

                try:
                    await self._process_goal_step(goal_id, goal)
                except Exception as e:
                    logger.error(f"Error processing goal {goal_id}: {e}")

    async def _process_goal_step(self, goal_id: str, goal: Dict[str, Any]) -> None:
        """Evaluate current step and push for completion."""
        plan = goal["plan"]
        idx = goal["current_step"]

        if idx >= len(plan):
            logger.info(f"Goal {goal_id} completed successfully.")
            goal["status"] = "completed"
            return

        step = plan[idx]
        agent_id = step["agent_id"]
        action = step["action"]
        criteria = step.get("success_criteria", "Execution successful")

        logger.info(f"Pushing goal {goal_id}, Step {idx}: {agent_id} -> {action}")

        # In a real system, we'd call the Mind to dispatch this.
        # For this implementation, we'll assume the Mind handles the dispatching
        # and we just track the state if the Mind provides feedback.
        # But wait, the PlanningAgent SHOULD be the one calling the agents if it's autonomous.

        # I need a reference to the Mind or a way to dispatch tasks.
        # Since I'm an agent, I can use my mcp_server or a heart reference to reach the Mind.

        heart = getattr(self, "_heart_ref", None)
        if heart and hasattr(heart, "_mind_ref"):
            mind = heart._mind_ref
            result = await mind.agents[agent_id].handle(
                AgentTask(content=action, intents=[agent_id]),
                context={"goal_id": goal_id, "step_index": idx},
            )

            # Verify result against criteria
            verification_prompt = (
                f"Verify if the following agent output fulfills the requirement: '{criteria}'.\n"
                f"Output: {result.summary}\n"
                f"Data: {json.dumps(result.data)}\n"
                "Respond with 'FULFILLED' or 'INCOMPLETE: [reason]'"
            )

            v_res = await self.llm_client.generate(
                verification_prompt, ModelCapability.UTILITY
            )
            if "FULFILLED" in v_res.text.upper():
                goal["current_step"] += 1
                goal["results"].append(
                    {"step": idx, "ok": True, "summary": result.summary}
                )
                logger.info(f"Step {idx} fulfilled.")
            else:
                logger.warning(
                    f"Step {idx} incomplete: {v_res.text}. Pushing again in next cycle."
                )
                goal["results"].append({"step": idx, "ok": False, "reason": v_res.text})
