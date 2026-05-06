from __future__ import annotations
import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents import (
    AgentResult,
    AgentTask,
    BaseAgent,
    CodingAgent,
    MemoryAgent,
    MonitoringAgent,
    ParallelAgent,
    VisionAgent,
    VoiceAgent,
    HermesAgent,
    ClawAgent,
    ThinkingAgent,
    EmotionAgent,
    LearningAgent,
    RoutingAgent,
    HardwareAgent,
    SelfUpdateAgent,
    SecurityAgent,
    OrchestratorAgent,
    PlanningAgent,
    TalkingAgent,
    SystemAgent,
    DashboardAgent,
)
from core.heart import Heart
from core.llm_client import LLMClient, ModelCapability
from mcp_tools.system_mcp import SystemMCPServer, create_default_system_mcp

logger = logging.getLogger("jarvis.mind")


@dataclass(frozen=True)
class MindEvent:
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class MindDecision:
    response: str
    intent: str
    agents: list[str]
    results: list[AgentResult] = field(default_factory=list)
    llm: dict[str, Any] | None = None


class Mind:
    """Central reasoning engine and delegation layer."""

    def __init__(
        self,
        *,
        heart: Heart,
        llm_client: LLMClient,
        agents: list[BaseAgent],
        mcp_server: SystemMCPServer,
        project_root: str | Path = ".",
        consciousness_interval: float = 30.0,
        autonomy_enabled: bool = False,
    ) -> None:
        self.heart = heart
        self.heart._mind_ref = self  # Allow agents to reach back to Mind via Heart
        self.llm_client = llm_client
        self.agents = {agent.agent_id: agent for agent in agents}
        self.mcp_server = mcp_server
        self.project_root = Path(project_root)
        self.consciousness_interval = consciousness_interval
        self.autonomy_enabled = autonomy_enabled
        self.history: list[MindEvent] = []
        self.skill_candidates: list[dict[str, Any]] = []
        self.active_plan: list[dict[str, Any]] | None = None
        self.plan_summary: str | None = None
        self.thinking: bool = False
        self.current_thought: str = ""
        self._consciousness_task: asyncio.Task[None] | None = None

    @classmethod
    def default(cls, project_root: str | Path = ".") -> "Mind":
        import os
        from core.providers import gemini_provider, nvidia_provider, ollama_provider

        # 1. Initialize Dynamic LLM Orchestrator
        brain_mode = os.getenv("JARVIS_BRAIN_MODE", "nvidia")
        default_cap = ModelCapability.BALANCED
        if brain_mode == "nvidia":
            default_cap = ModelCapability.HEAVY
        elif brain_mode == "gemini":
            default_cap = ModelCapability.UTILITY
        autonomy_enabled = os.getenv("JARVIS_AUTONOMY_ENABLED", "0") == "1"

        llm_client = LLMClient(default_capability=default_cap)
        llm_client.register_provider("nvidia", nvidia_provider)
        llm_client.register_provider("ollama", ollama_provider)
        llm_client.register_provider("gemini", gemini_provider)

        # 2. Initialize Body Parts (Agents)
        mcp_server = create_default_system_mcp(project_root=project_root)
        agents: list[BaseAgent] = [
            OrchestratorAgent(mcp_server, llm_client=llm_client),
            MemoryAgent(mcp_server),
            CodingAgent(mcp_server, llm_client=llm_client),
            PlanningAgent(mcp_server, llm_client=llm_client),
            VisionAgent(mcp_server),
            MonitoringAgent(mcp_server),
            ParallelAgent(mcp_server),
            VoiceAgent(mcp_server),
            TalkingAgent(mcp_server),
            HermesAgent(mcp_server),
            ClawAgent(mcp_server),
            ThinkingAgent(mcp_server, llm_client=llm_client),
            EmotionAgent(mcp_server, llm_client=llm_client),
            LearningAgent(mcp_server, llm_client=llm_client),
            RoutingAgent(mcp_server, llm_client=llm_client),
            HardwareAgent(mcp_server),
            SecurityAgent(mcp_server),
            SystemAgent(mcp_server),
            DashboardAgent(mcp_server),
        ]

        # Link Evolution Engine to Coding Agent
        coding_agent = next(a for a in agents if a.agent_id == "coding")
        agents.append(SelfUpdateAgent(mcp_server, coding_agent=coding_agent))

        # 3. Initialize Heart (Identity)
        heart = Heart()

        # Wire LLM Failure Reporting
        orchestrator = next(a for a in agents if a.agent_id == "orchestrator")
        llm_client.on_failure = orchestrator.report_failure
        heart.set_digital_footprint(
            gmail=os.getenv("JARVIS_EMAIL"),
            github=os.getenv("JARVIS_GITHUB_TOKEN"),
            hugging_face=os.getenv("JARVIS_HF_TOKEN"),
        )

        # 4. Finalize Agent References
        for agent in agents:
            if hasattr(agent, "_heart_ref"):
                agent._heart_ref = heart
            # Specifically for VisionAgent and HardwareAgent which have proactive loops
            if agent.agent_id in ["vision", "proprioception", "monitoring"]:
                setattr(agent, "_heart_ref", heart)

        return cls(
            heart=heart,
            llm_client=llm_client,
            agents=agents,
            mcp_server=mcp_server,
            project_root=project_root,
            autonomy_enabled=autonomy_enabled,
        )

    async def start_consciousness(self) -> None:
        # Initialize agents. Autonomous/background loops are opt-in.
        autonomous_agents = {
            "thinking",
            "learning",
            "learning_center",
            "vision",
            "proprioception",
            "planning_agent",
            "hermes",
        }
        initializers = [
            (agent_id, agent.initialize())
            for agent_id, agent in self.agents.items()
            if hasattr(agent, "initialize")
            and (self.autonomy_enabled or agent_id not in autonomous_agents)
        ]
        init_results = await asyncio.gather(
            *(initializer for _, initializer in initializers),
            return_exceptions=True,
        )
        for (agent_id, _), result in zip(initializers, init_results):
            if isinstance(result, Exception):
                logger.error(f"Failed to initialize agent {agent_id}: {result}")
            elif result is False:
                logger.warning(f"Agent {agent_id} reported initialization failure.")

        if self.autonomy_enabled and (
            self._consciousness_task is None or self._consciousness_task.done()
        ):
            self._consciousness_task = asyncio.create_task(self._consciousness_loop())

    async def handle_event(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> MindDecision:
        metadata = metadata or {}
        event = MindEvent(content=content, metadata=metadata)
        self.history.append(event)
        logger.debug(f"Handling event: {content[:50]}...")

        self.thinking = True
        self.current_thought = "Analyzing input intent..."

        # 0. Planning Override (Confirmation Logic)
        has_active_goal = False
        if "planning_agent" in self.agents:
            has_active_goal = (
                len(getattr(self.agents["planning_agent"], "active_goals", {})) > 0
            )

        if (self.active_plan or has_active_goal) and any(
            word in content.lower()
            for word in [
                "execute",
                "confirm",
                "proceed",
                "yes",
                "do it",
                "start",
                "affirmative",
                "correct",
            ]
        ):
            await self._narrate("Confirmed, sir. Resuming multi-step mission protocol.")
            if self.active_plan:
                return await self._execute_active_plan(metadata)
            else:
                # Trigger the next step of the active goal in PlanningAgent
                planning_task = AgentTask(
                    content="proceed with next step", intents=["execute_plan"]
                )
                return await self.agents["planning_agent"].handle(
                    planning_task, context=self._context()
                )

        # 0.1 Direct File Plan Execution
        if "execute" in content.lower() and (
            ".txt" in content.lower() or ".json" in content.lower()
        ):
            # Extract potential path (handles quotes and spaces)
            path_match = re.search(
                r'["\']?([a-zA-Z]:\\[^"\']+|\/[\w/\.-]+)["\']?', content
            )
            if path_match:
                path = path_match.group(1)
                if os.path.exists(path):
                    await self._narrate(
                        f"Accessing plan from local storage at {os.path.basename(path)}."
                    )
                    try:
                        with open(path, "r") as f:
                            plan_text = f.read()
                        # Register this as the active plan and execute
                        # We delegate to PlanningAgent to structure it
                        planning_task = AgentTask(
                            content=f"Create a structured multi-step plan based on this mission document: {plan_text}",
                            intents=["plan"],
                        )
                        plan_result = await self.agents["planning_agent"].handle(
                            planning_task
                        )
                        if plan_result.handled and "plan" in plan_result.data:
                            self.active_plan = plan_result.data["plan"]
                            return await self._execute_active_plan(metadata)
                    except Exception as e:
                        logger.error(f"Failed to read plan file: {e}")
                        await self._narrate(
                            "Apologies, sir. I encountered a fault while reading the plan file."
                        )

        # 1. Dynamic Semantic Routing
        routing_task = AgentTask(content=content, intents=["route"])
        agents_meta = {aid: a.describe() for aid, a in self.agents.items()}
        routing_result = await self.agents["semantic_router"].handle(
            routing_task, context={"agents_metadata": agents_meta}
        )

        intents = routing_result.data.get("intents", ["conversation"])
        selected_ids = routing_result.data.get("selected_agents", [])
        urgency = routing_result.data.get("urgency", 0.5)

        # 2. Body Part Selection
        task = AgentTask(content=content, intents=intents, metadata=metadata)
        selected_agents = [
            self.agents[aid] for aid in selected_ids if aid in self.agents
        ]

        # Always include core meta-sensors
        for sensor in [
            "emotion_sensor",
            "monitoring",
            "proprioception",
            "immune_system",
        ]:
            if sensor in self.agents and self.agents[sensor] not in selected_agents:
                selected_agents.append(self.agents[sensor])

        # 3. Parallel Execution
        # Fetch relevant memories to 'link' all agents together
        memories = []
        if "memory" in self.agents:
            mem_result = await self.agents["memory"].handle(
                AgentTask(content=content, intents=["recall"])
            )
            if mem_result.handled:
                memories = mem_result.data.get("results", [])

        context = self._context()
        context["relevant_memories"] = memories
        context["history"] = [
            f"{e.created_at}: {e.content}" for e in self.history[-10:]
        ]
        context["agents_metadata"] = agents_meta

        self.current_thought = "Synthesizing agent results into a cohesive response..."
        raw_results = await asyncio.gather(
            *(agent.handle(task, context=context) for agent in selected_agents),
            return_exceptions=True,
        )

        results = list(
            self._normalize_agent_result(agent, result)
            for agent, result in zip(selected_agents, raw_results)
        )

        # 4. Security Gatekeeper Enforcement
        security = self.agents.get("immune_system")
        if security:
            # Check if all selected agents are authorized
            unauthorized = [
                a.agent_id
                for a in selected_agents
                if not security.is_authorized(a.agent_id)
            ]
            if unauthorized:
                logger.warning(
                    f"Security Block: Unauthorized access attempt for {unauthorized}"
                )
                # Filter results to remove unauthorized data
                results = [r for r in results if r.agent_id not in unauthorized]
                # Inject security failure message
                results.append(
                    AgentResult(
                        agent_id="immune_system",
                        handled=False,
                        summary=f"Security Alert: High-privilege agents {unauthorized} were blocked due to identity mismatch.",
                        confidence=1.0,
                    )
                )

        # 5. Intelligent Synthesis & Orchestration
        self.current_thought = "Auditing resources and selecting best brain..."
        required_cap = ModelCapability.BALANCED
        orchestrator = self.agents.get("orchestrator") or self.agents.get(
            "orchestration"
        )

        if orchestrator:
            orch_result = await orchestrator.handle(task, context=context)
            if orch_result.handled:
                required_cap = orch_result.data.get("required_cap") or required_cap
                self.current_thought = orch_result.summary

        self.current_thought = "Synthesizing agent results into natural language..."
        if self.llm_client:
            synthesis_prompt = self._synthesis_prompt(content, results)

            # Determine synthesis capability based on orchestrator and urgency
            cap = required_cap
            if urgency > 0.8:
                cap = ModelCapability.LIGHT  # Speed over depth for urgency
            elif any("complex" in intent for intent in intents):
                cap = ModelCapability.HEAVY

            llm_response = await self.llm_client.generate(
                synthesis_prompt,
                cap,
                purpose="synthesis",
                metadata={"urgency": urgency},
                fallback=True,
            )
            response = llm_response.text
            self.current_thought = (
                f"Response via {llm_response.provider} [{llm_response.model_id}]"
            )
        else:
            # Fallback to basic synthesis if LLM is unavailable
            self.current_thought = "Using offline synthesis (No LLM client)..."
            final_urgency = self.heart.emotion.intensity
            response = self._synthesize_agent_results(
                task, results, urgency=final_urgency
            )

        # Check for new plan generation
        for result in results:
            if (
                result.agent_id == "planning_agent"
                and result.data.get("status") == "planned"
            ):
                self.active_plan = result.data.get("plan")
                self.plan_summary = result.summary

        # 6. Autonomous Evolution Trigger
        self.current_thought = "Checking for evolutionary triggers..."
        for result in results:
            if result.handled and "evolution_plan" in result.data:
                plan = result.data["evolution_plan"]
                logger.info(
                    f"Evolution plan detected: {plan.get('feature')}. Triggering Evolution Engine."
                )
                if self.autonomy_enabled and "evolution_engine" in self.agents:
                    asyncio.create_task(
                        self.agents["evolution_engine"].handle(
                            AgentTask(
                                content="evolve",
                                intents=["evolve"],
                                metadata={"plan": plan},
                            )
                        )
                    )

        # 7. Voice Feedback (Mouth)
        if self.heart.voice.tts_enabled and "talking" in self.agents:
            self.current_thought = "Preparing vocal response..."
            asyncio.create_task(
                self.agents["talking"].handle(
                    AgentTask(
                        content=response,
                        intents=["talk"],
                        metadata={
                            "response_text": response,
                            "emotion": self.heart.emotion.name,
                            "intensity": self.heart.emotion.intensity,
                        },
                    )
                )
            )
        elif self.heart.voice.tts_enabled and "voice" in self.agents:
            self.current_thought = "Preparing vocal response..."
            asyncio.create_task(
                self.agents["voice"].handle(
                    AgentTask(
                        content=response,
                        intents=["speak"],
                        metadata={"emotion": self.heart.emotion.name},
                    )
                )
            )

        # 8. Long-term Memory Recording (Async)
        if "memory" in self.agents:
            self.current_thought = "Recording interaction to long-term memory..."
            asyncio.create_task(
                self.agents["memory"].handle(
                    AgentTask(
                        content=content,
                        intents=["record"],
                        metadata={
                            "response": response,
                            "results": [r.data for r in results],
                        },
                    )
                )
            )

        # 7. Finalize
        self.thinking = False
        self.current_thought = ""

        return MindDecision(
            response=self.heart.compose_friend_response(response),
            intent=", ".join(intents),
            agents=[agent.agent_id for agent in selected_agents],
            results=list(results),
        )

    async def _execute_active_plan(self, metadata: dict[str, Any]) -> MindDecision:
        """Execute the stored multi-step plan."""
        self.current_thought = "Executing multi-step plan..."
        import json

        all_results = []
        plan = self.active_plan or []
        self.active_plan = None  # Clear after starting
        if not plan:
            self.thinking = False
            self.current_thought = ""
            return MindDecision(
                response=self.heart.compose_friend_response(
                    "No active plan is loaded for execution."
                ),
                intent="plan_execution",
                agents=[],
                results=[],
            )

        for step in plan:
            agent_id = step.get("agent_id")
            action = step.get("action")
            description = step.get("description")

            if agent_id in self.agents:
                self.current_thought = f"Executing: {description}..."
                await self._narrate(description)
                task = AgentTask(content=action, intents=[agent_id], metadata=metadata)
                result = await self.agents[agent_id].handle(
                    task, context=self._context()
                )
                all_results.append(result)

        # Synthesis of results
        synthesis_prompt = self._synthesis_prompt("Plan Execution Results", all_results)
        llm_response = await self.llm_client.generate(
            synthesis_prompt, ModelCapability.BALANCED, purpose="plan_execution"
        )

        self.thinking = False
        self.current_thought = ""
        return MindDecision(
            response=llm_response.text,
            intent="plan_execution",
            agents=[r.agent_id for r in all_results],
            results=all_results,
            llm={"model": llm_response.model_id, "provider": llm_response.provider},
        )

    async def _narrate(self, text: str):
        """Proactively narrate internal state or actions via TTS."""
        if (
            not self.autonomy_enabled
            or not self.heart.voice.tts_enabled
            or "talking" not in self.agents
        ):
            return

        # Use talking agent for narration
        asyncio.create_task(
            self.agents["talking"].handle(
                AgentTask(
                    content=text,
                    intents=["talk"],
                    metadata={
                        "response_text": text,
                        "emotion": "analytical",
                        "intensity": 0.3,
                    },
                )
            )
        )

    async def reflect(self) -> dict[str, Any]:
        memory = self.agents.get("memory")
        reflection: AgentResult | None = None
        if isinstance(memory, MemoryAgent):
            reflection = await memory.reflect()

        candidates = self.skill_discovery_protocol()
        return {
            "reflection": reflection.data if reflection else {},
            "skill_candidates": candidates,
        }

    def skill_discovery_protocol(self) -> list[dict[str, Any]]:
        recent = self.history[-20:]
        repeated: dict[str, int] = {}
        for event in recent:
            intent = self._infer_intent(event.content)
            self.current_thought = f"Intent identified: {intent}. Activating agents..."
            repeated[intent] = repeated.get(intent, 0) + 1

        for intent, count in repeated.items():
            if count >= 3 and not any(
                item["intent"] == intent for item in self.skill_candidates
            ):
                self.skill_candidates.append(
                    {
                        "intent": intent,
                        "reason": f"Observed {count} recent event(s) with this intent.",
                        "status": "candidate",
                    }
                )
        return list(self.skill_candidates)

    @staticmethod
    def _infer_intent(content: str) -> str:
        text = content.lower()
        if any(k in text for k in ("plan", "strategy", "roadmap")):
            return "planning"
        if any(k in text for k in ("code", "bug", "fix", "refactor", "file")):
            return "coding"
        if any(k in text for k in ("voice", "speak", "audio", "tts")):
            return "voice"
        if any(k in text for k in ("camera", "vision", "screen", "screenshot")):
            return "vision"
        return "conversation"

    def self_awareness(self) -> dict[str, Any]:
        return {
            "nature": (
                "J.A.R.V.I.S. 2.0 - An advanced autonomous AI entity. I feature a dynamic Model Orchestrator "
                "that allows me to autonomously choose between NVIDIA, Ollama, and Gemini 'brains' "
                "based on task complexity, cost, and speed requirements."
            ),
            "heart": self.heart.get_context(),
            "mind": {"history_events": len(self.history)},
            "agents": {
                agent_id: agent.describe() for agent_id, agent in self.agents.items()
            },
            "model_registry": [m.id for m in self.llm_client.registry],
        }

    async def _consciousness_loop(self) -> None:
        """The constant background consciousness of J.A.R.V.I.S."""
        logger.info("Neural consciousness loop started.")
        while True:
            try:
                # 1. Self-Reflection (Thinking)
                if "thinking" in self.agents:
                    await self.agents["thinking"].handle(
                        AgentTask(content="Internal reflection", intents=["think"])
                    )

                # 2. Resource Audit (Orchestrator)
                if "orchestrator" in self.agents:
                    await self.agents["orchestrator"].handle(
                        AgentTask(content="Audit resources", intents=["audit"])
                    )

                # 3. Learning & Evolution Insight
                if "learning_center" in self.agents:
                    await self.agents["learning_center"].handle(
                        AgentTask(content="Analyze history", intents=["learn"])
                    )

                # 4. Neural Sleep (Wait for next cycle)
                await asyncio.sleep(self.consciousness_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Consciousness loop error: {e}")
                await asyncio.sleep(5)

    def _context(self) -> dict[str, Any]:
        return {
            "project_root": str(self.project_root),
            "heart": self.heart,
            "heart_data": self.heart.get_context(),
            "self_awareness": self.self_awareness(),
        }

    def _synthesis_prompt(self, user_input: str, results: list[AgentResult]) -> str:
        import json

        identity = self.heart.get_context()
        detailed_statuses: list[str] = []
        for result in results:
            if result.agent_id in ("emotion_sensor", "semantic_router"):
                continue
            status = "success" if result.handled else "failed"
            if isinstance(result.data, dict):
                status = str(result.data.get("status", status))
            detailed_statuses.append(
                f"- {result.agent_id} [{status}]: {result.summary}"
            )
        summaries = "\n".join(detailed_statuses) or "- No execution results."

        # Sensory & History Status
        history_str = "\n".join([f"User: {e.content}" for e in self.history[-5:]])
        eyes = "Online" if identity.get("vision", {}).get("enabled") else "Offline"
        ears = "Listening" if identity.get("voice", {}).get("enabled") else "Muted"
        security = (
            "Verified"
            if identity.get("identity", {}).get("authenticated")
            else "Advisory"
        )

        plan_prompt = ""
        if self.active_plan:
            plan_prompt = f"\n\n## Active Plan (Awaiting Confirmation):\n{self.plan_summary}\nSteps: {json.dumps(self.active_plan, indent=2)}\n"

        return (
            f"{self.heart.personality_prompt()}\n"
            f"Current Emotional State: {identity.get('emotion', {}).get('name', 'calm')}\n"
            f"Sensory Status: Eyes [{eyes}] | Ears [{ears}] | Security [{security}]\n"
            f"## Conversation History (Last 5):\n{history_str}\n\n"
            "## Task Results from Body Parts:\n"
            f"{summaries}\n\n"
            f"{plan_prompt}"
            "## Current User Input:\n"
            f"{user_input}\n\n"
            "Based on the results above, provide a natural, human-like response to the user. "
            "Never claim an action completed unless the corresponding status is exactly 'success'. "
            "If status is 'simulated' or 'failed', clearly say it did not execute and why. "
            "If an action was taken, confirm it. If data was retrieved, share it naturally. "
            "If security fallback (Camera) was used, mention it briefly but reassuringly. "
            "If a plan is active, explicitly ask the user for confirmation to execute."
            "Stay in character as J.A.R.V.I.S."
        )

    def _conversation_prompt(self, content: str) -> str:
        identity = self.heart.get_context()
        emotion = identity.get("emotion", {})
        mood = emotion.get("name", "calm")
        urgency = emotion.get("intensity", 0.5)

        style_hint = ""
        if urgency > 0.8:
            style_hint = "The user is in a HUGE HURRY. Be extremely concise, use bullet points, and skip all fluff. Just the facts/actions."
        elif mood == "frustrated":
            style_hint = "The user seems frustrated. Be extra helpful and empathetic, but stay professional."

        return (
            f"{self.heart.personality_prompt()}\n"
            f"Style Hint: {style_hint}\n"
            f"Current Emotional State: {mood} (Urgency: {urgency})\n"
            f"Current Identity/Digital Footprint: {identity}\n\n"
            f"User: {content}\nJ.A.R.V.I.S.:"
        )

    @staticmethod
    def _synthesize_agent_results(
        task: AgentTask, results: list[AgentResult], urgency: float = 0.5
    ) -> str:
        summaries = []
        for result in results:
            if result.handled and result.agent_id not in (
                "emotion_sensor",
                "semantic_router",
            ):  # Filter out meta-results
                text = result.summary
                if urgency < 0.8 and result.data and "result" in result.data:
                    text += f"\n\n{result.data['result']}"
                summaries.append(text)

        if not summaries:
            # If no agent handled it or only meta-agents ran, fall back to LLM synthesis of the task
            return f"Thinking about: {task.content}"

        if urgency > 0.8:
            # Concise summary for urgent tasks
            return f"Actioned {', '.join(task.intents)}: {' | '.join(summaries)}"

        return f"delegated task to the right body parts. {' '.join(summaries)}"

    @staticmethod
    def _normalize_agent_result(
        agent: BaseAgent,
        result: AgentResult | BaseException,
    ) -> AgentResult:
        if isinstance(result, AgentResult):
            return result
        logger.error(
            "Agent %s failed while handling a task",
            agent.agent_id,
            exc_info=(type(result), result, result.__traceback__),
        )
        return AgentResult(
            agent_id=agent.agent_id,
            handled=False,
            summary=f"{agent.agent_id} failed: {result}",
            data={"error": str(result)},
            confidence=0.0,
        )

    async def stop_consciousness(self) -> None:
        """Gracefully stop background neural loops."""
        if self._consciousness_task and not self._consciousness_task.done():
            self._consciousness_task.cancel()
            try:
                await self._consciousness_task
            except asyncio.CancelledError:
                pass
        self._consciousness_task = None
        logger.info("Mind consciousness deactivated.")
