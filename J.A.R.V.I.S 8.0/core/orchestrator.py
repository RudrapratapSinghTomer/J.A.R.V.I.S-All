import os
import re
import yaml
from typing import TypedDict, List, Optional
from langgraph.graph import StateGraph, END
from openai import OpenAI

# Load config once
_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
with open(_CONFIG_PATH, "r") as _f:
    _CFG = yaml.safe_load(_f)

_CLOUD_CFG = _CFG.get("models", {}).get("cloud", {})
_NVIDIA_BASE = _CLOUD_CFG.get("api_base", "https://integrate.api.nvidia.com/v1")
_MOE_MODEL = _CLOUD_CFG.get("moe", "mistralai/mixtral-8x22b-instruct-v0.1")
_DEFAULT_LRM = _CLOUD_CFG.get("lrm", "meta/llama-3.1-70b-instruct")

class AgentState(TypedDict):
    query: str
    user_id: str
    context: str
    route: str
    plan: List[str]
    actions: List[dict]
    result: str
    errors: List[str]

JARVIS_SYSTEM_PROMPT = (
    "You are JARVIS (Just A Rather Very Intelligent System) — a sophisticated, "
    "multi-modal agentic AI assistant. You are precise, proactive, and always speak "
    "with clarity and confidence. You reason step-by-step, surface key insights, and "
    "never guess when you can verify."
)

_SPECIALIST_SYSTEM = (
    JARVIS_SYSTEM_PROMPT + "\n\n"
    "You are currently acting as the SPECIALIST module. You excel at technical reasoning."
)

class Orchestrator:
    def __init__(self, router, mhc_memory, researcher, executor, vision=None):
        self.router = router
        self.memory = mhc_memory
        self.researcher = researcher
        self.executor = executor
        self.vision = vision

        # Build NIM clients
        nvidia_key = os.getenv("NVIDIA_API_KEY")
        self._nim_client = OpenAI(base_url=_NVIDIA_BASE, api_key=nvidia_key) if nvidia_key else None
        self._nim_model = os.getenv("NVIDIA_MODEL", _DEFAULT_LRM)
        self._moe_model = _MOE_MODEL

        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(AgentState)

        workflow.add_node("ingestion", self.ingestion_node)
        workflow.add_node("routing", self.routing_node)
        workflow.add_node("vision", self.vision_node)
        workflow.add_node("local_slm_execution", self.local_slm_node)
        workflow.add_node("cloud_planning", self.cloud_planning_node)
        workflow.add_node("specialist", self.specialist_node)
        workflow.add_node("research", self.research_node)
        workflow.add_node("action_execution", self.action_execution_node)
        workflow.add_node("memory_mapping", self.memory_mapping_node)

        workflow.set_entry_point("ingestion")
        workflow.add_edge("ingestion", "routing")

        workflow.add_conditional_edges(
            "routing",
            self._dispatch_after_routing,
            {
                "vision": "vision",
                "OLLAMA": "local_slm_execution",
                "NVIDIA_NIM": "cloud_planning",
                "specialist": "specialist",
            },
        )

        workflow.add_edge("vision", "memory_mapping")
        workflow.add_edge("local_slm_execution", "memory_mapping")
        workflow.add_edge("specialist", "memory_mapping")

        workflow.add_conditional_edges(
            "cloud_planning",
            self._route_after_plan,
            {
                "research": "research",
                "action": "action_execution",
                "finish": "memory_mapping",
            },
        )

        workflow.add_edge("research", "cloud_planning")
        workflow.add_edge("action_execution", "cloud_planning")
        workflow.add_edge("memory_mapping", END)

        return workflow.compile()

    def _dispatch_after_routing(self, state: AgentState) -> str:
        query = state["query"].lower()
        if any(kw in query for kw in ["[screen]", "[image:", "screenshot", "what do you see"]):
            return "vision"
        if any(kw in query for kw in ["code", "math", "algorithm", "debug"]):
            return "specialist"
        if any(kw in query for kw in ["run", "terminal", "mkdir", "npm", "pip", "shell", "execute"]):
            return "NVIDIA_NIM" # Route to cloud_planning
        return state["route"]

    def _route_after_plan(self, state: AgentState) -> str:
        plan = state.get("plan", [])
        if not plan:
            return "finish"
        return plan[0]

    def ingestion_node(self, state: AgentState):
        user_id = state.get("user_id", "default_user")
        context = self.memory.get_context(user_id, state["query"])
        return {"context": context, "user_id": user_id}

    def routing_node(self, state: AgentState):
        route = self.router.route(state["query"])
        return {"route": route}

    def vision_node(self, state: AgentState):
        if not self.vision:
            return {"result": "Vision module not initialized."}
        query = state["query"]
        source = "screen" if "[screen]" in query.lower() or "screenshot" in query.lower() else "screen"
        prompt = query.replace("[screen]", "").strip()
        result = self.vision.analyze(source, prompt)
        return {"result": result}

    def local_slm_node(self, state: AgentState):
        query = state["query"]
        context = state.get("context", "")
        prompt = f"{JARVIS_SYSTEM_PROMPT}\n\nContext:\n{context}\n\nUser: {query}\nJARVIS:"
        try:
            from core.router import OLLAMA_URL, SLM_MODEL
            import requests
            response = requests.post(
                f"{OLLAMA_URL}/generate",
                json={"model": SLM_MODEL, "prompt": prompt, "stream": False},
                timeout=60,
            )
            response.raise_for_status()
            return {"result": response.json().get("response", "Error processing locally.")}
        except Exception as e:
            return {"result": f"Local SLM connection failed: {e}"}

    def cloud_planning_node(self, state: AgentState):
        if not self._nim_client:
            return {"result": "NVIDIA API key missing. Cannot use cloud planner."}
        query = state["query"]
        messages = [
            {"role": "system", "content": JARVIS_SYSTEM_PROMPT},
            {"role": "user", "content": f"Context: {state.get('context','')}\n\nQuery: {query}"},
        ]
        try:
            completion = self._nim_client.chat.completions.create(
                model=self._nim_model, messages=messages, temperature=0.2, max_tokens=1024
            )
            resp = completion.choices[0].message.content
            plan = ["research"] if "research" in query.lower() else (["action"] if "execute" in query.lower() else [])
            return {"plan": plan, "result": resp}
        except Exception as e:
            return {"result": f"Cloud call failed: {e}"}

    def specialist_node(self, state: AgentState):
        if not self._nim_client:
            return {"result": "NVIDIA API key missing. Specialist module offline."}
        try:
            completion = self._nim_client.chat.completions.create(
                model=self._moe_model,
                messages=[{"role": "system", "content": _SPECIALIST_SYSTEM}, {"role": "user", "content": state["query"]}],
                temperature=0.1,
                max_tokens=2048,
            )
            return {"result": completion.choices[0].message.content}
        except Exception as e:
            return self.cloud_planning_node(state)

    def research_node(self, state: AgentState):
        res = self.researcher.perform_deep_dive(state["query"])
        return {"result": res, "plan": []}

    def action_execution_node(self, state: AgentState):
        res = self.executor.execute_action(state["query"])
        return {"result": res, "plan": []}

    def memory_mapping_node(self, state: AgentState):
        self.memory.add_to_manifold(state["user_id"], f"Q: {state['query']} | A: {state.get('result','')[:200]}")
        return state

    def run(self, query: str, user_id: str = "default_user") -> str:
        initial_state = {"query": query, "user_id": user_id, "context": "", "route": "", "plan": [], "actions": [], "result": "", "errors": []}
        final_state = self.graph.invoke(initial_state)
        return final_state["result"]
