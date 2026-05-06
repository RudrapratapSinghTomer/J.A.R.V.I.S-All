import os
import re
import yaml
from typing import TypedDict, List, Optional

from langgraph.graph import StateGraph, END
from openai import OpenAI


# -----------------------------------------------------------------------
# Load config once at module level
# -----------------------------------------------------------------------
_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
with open(_CONFIG_PATH, "r") as _f:
    _CFG = yaml.safe_load(_f)

_CLOUD_CFG   = _CFG.get("models", {}).get("cloud", {})
_NVIDIA_BASE = _CLOUD_CFG.get("api_base", "https://integrate.api.nvidia.com/v1")
_MOE_MODEL   = _CLOUD_CFG.get("moe", "mistralai/mixtral-8x22b-instruct-v0.1")
_DEFAULT_LRM = _CLOUD_CFG.get("lrm", "meta/llama-3.1-70b-instruct")


# -----------------------------------------------------------------------
# State schema
# -----------------------------------------------------------------------
class AgentState(TypedDict):
    query: str
    user_id: str
    context: str
    route: str
    plan: List[str]
    actions: List[dict]
    result: str
    errors: List[str]


# -----------------------------------------------------------------------
# Jarvis system identity (necessary to define Jarvis's character)
# -----------------------------------------------------------------------
JARVIS_SYSTEM_PROMPT = (
    "You are JARVIS (Just A Rather Very Intelligent System) — a sophisticated, "
    "multi-modal agentic AI assistant. You are precise, proactive, and always speak "
    "with clarity and confidence. You reason step-by-step, surface key insights, and "
    "never guess when you can verify. When you have memory context from past interactions, "
    "use it to personalize your response without being asked. If a task requires coding, "
    "research, or physical action, you create a plan and execute it — you don't just describe it."
)

_SPECIALIST_SYSTEM = (
    JARVIS_SYSTEM_PROMPT + "\n\n"
    "You are currently acting as the SPECIALIST module. You excel at coding, "
    "mathematics, data analysis, and domain-specific technical reasoning. "
    "Provide precise, complete, and well-commented solutions."
)


# -----------------------------------------------------------------------
# Orchestrator
# -----------------------------------------------------------------------
class Orchestrator:
    def __init__(self, router, mhc_memory, researcher, executor, vision=None):
        self.router     = router
        self.memory     = mhc_memory
        self.researcher = researcher
        self.executor   = executor
        self.vision     = vision  # Optional VisionVLM instance

        # Build NIM clients once — avoids repeated env reads per node call
        nvidia_key = os.getenv("NVIDIA_API_KEY")
        self._nim_client  = OpenAI(base_url=_NVIDIA_BASE, api_key=nvidia_key)
        self._nim_model   = os.getenv("NVIDIA_MODEL", _DEFAULT_LRM)
        self._moe_model   = _MOE_MODEL

        self.graph = self._build_graph()

    # ------------------------------------------------------------------
    # Graph wiring
    # ------------------------------------------------------------------
    def _build_graph(self):
        workflow = StateGraph(AgentState)

        workflow.add_node("ingestion",           self.ingestion_node)
        workflow.add_node("routing",             self.routing_node)
        workflow.add_node("vision",              self.vision_node)
        workflow.add_node("local_slm_execution", self.local_slm_node)
        workflow.add_node("cloud_planning",      self.cloud_planning_node)
        workflow.add_node("specialist",          self.specialist_node)
        workflow.add_node("research",            self.research_node)
        workflow.add_node("action_execution",    self.action_execution_node)
        workflow.add_node("memory_mapping",      self.memory_mapping_node)

        workflow.set_entry_point("ingestion")
        workflow.add_edge("ingestion", "routing")

        workflow.add_conditional_edges(
            "routing",
            self._dispatch_after_routing,
            {
                "vision":            "vision",
                "OLLAMA":            "local_slm_execution",
                "NVIDIA_NIM":        "cloud_planning",
                "specialist":        "specialist",
            },
        )

        workflow.add_edge("vision",              "memory_mapping")
        workflow.add_edge("local_slm_execution", "memory_mapping")
        workflow.add_edge("specialist",          "memory_mapping")

        workflow.add_conditional_edges(
            "cloud_planning",
            self._route_after_plan,
            {
                "research": "research",
                "action":   "action_execution",
                "finish":   "memory_mapping",
            },
        )

        workflow.add_edge("research",         "cloud_planning")
        workflow.add_edge("action_execution", "cloud_planning")
        workflow.add_edge("memory_mapping",   END)

        return workflow.compile()

    # ------------------------------------------------------------------
    # Routing helpers
    # ------------------------------------------------------------------
    def _dispatch_after_routing(self, state: AgentState) -> str:
        query = state["query"]
        q     = query.lower()

        if self._is_vision_query(query):
            return "vision"

        specialist_kws = [
            "code", "script", "algorithm", "function", "math", "formula",
            "calculate", "analyze data", "debug", "refactor", "sql",
        ]
        if any(k in q for k in specialist_kws):
            return "specialist"

        # Falls through to the LLM-router result (OLLAMA or NVIDIA_NIM)
        return state["route"]

    def _is_vision_query(self, query: str) -> bool:
        vision_kws = [
            "[screen]", "[image:", "screenshot", "what's on my screen",
            "what do you see", "look at my screen", "analyze screen",
            "process image", "describe image",
        ]
        q = query.lower()
        return any(k in q for k in vision_kws)

    def _route_after_plan(self, state: AgentState) -> str:
        """
        FIX: Do NOT mutate state["plan"] with .pop().
        LangGraph merges state dicts between nodes — mutating the list
        directly causes race conditions and unexpected re-routing.
        Instead, read the first element without modifying the list;
        the list will naturally drain as cloud_planning rebuilds it each loop.
        """
        plan = state.get("plan", [])
        if not plan:
            return "finish"
        return plan[0]  # Peek, don't pop

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------
    def ingestion_node(self, state: AgentState):
        user_id = state.get("user_id", "default_user")
        context = self.memory.get_context(user_id, state["query"])
        return {"context": context, "user_id": user_id}

    def routing_node(self, state: AgentState):
        route = self.router.route(state["query"])
        return {"route": route}

    # --- Vision ---
    def vision_node(self, state: AgentState):
        """
        Handles [screen] and [image: <path/url>] queries.
        """
        query = state["query"]

        if self.vision is None:
            return {"result": "[Vision] VisionVLM not initialized. Pass a VisionVLM instance to Orchestrator."}

        image_tag = re.search(r"\[image:\s*(.+?)\]", query, re.IGNORECASE)
        if image_tag:
            source = image_tag.group(1).strip()
            prompt = query.replace(image_tag.group(0), "").strip()
        elif re.search(r"\[screen\]|screenshot", query, re.IGNORECASE):
            source = "screen"
            prompt = re.sub(r"\[screen\]", "", query, flags=re.IGNORECASE).strip()
        else:
            source = "screen"
            prompt = query

        if not prompt:
            prompt = "Describe everything you see in detail."

        print(f"[Vision] Analyzing source='{source}' with prompt='{prompt[:80]}'...")
        result = self.vision.analyze(source, prompt)
        return {"result": result}

    # --- Local SLM (Edge Guard) ---
    def local_slm_node(self, state: AgentState):
        query   = state["query"]
        context = state.get("context", "")

        ctx_block = f"Context from memory:\n{context}\n\n" if context else ""
        prompt = f"{JARVIS_SYSTEM_PROMPT}\n\n{ctx_block}User: {query}\nJARVIS:"

        try:
            from core.router import OLLAMA_URL, SLM_MODEL
            import requests

            response = requests.post(
                f"{OLLAMA_URL}/generate",
                json={"model": SLM_MODEL, "prompt": prompt, "stream": False},
                timeout=60,
            )
            response.raise_for_status()
            result = response.json().get(
                "response", "I encountered an error processing your request locally."
            )
        except Exception as e:
            print(f"[Orchestrator] Local SLM Error: {e}")
            result = f"Local SLM connection failed. Ensure Ollama is running. (Error: {e})"

        return {"result": result}

    # --- Cloud Planner (LRM) ---
    def cloud_planning_node(self, state: AgentState):
        query         = state["query"]
        context       = state.get("context", "")
        result_so_far = state.get("result", "")

        user_content = ""
        if context:
            user_content += f"Memory Context:\n{context}\n\n"
        if result_so_far:
            user_content += f"Previous step result:\n{result_so_far}\n\n"
        user_content += f"User Query: {query}"

        messages = [
            {"role": "system", "content": JARVIS_SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ]

        try:
            completion = self._nim_client.chat.completions.create(
                model=self._nim_model,
                messages=messages,
                temperature=0.2,
                max_tokens=1024,
            )
            response_text = completion.choices[0].message.content

            # Detect next action from query intent
            plan = []
            q = query.lower()
            if any(k in q for k in ["research", "find", "search", "look up", "what is", "how does"]):
                plan = ["research"]
            elif any(k in q for k in ["write", "create", "execute", "run", "add",
                                       "commit", "push", "readme", "git", "file",
                                       "make", "build", "generate"]):
                plan = ["action"]

            return {"plan": plan, "result": response_text}

        except Exception as e:
            print(f"[Orchestrator] Cloud Model Error: {e}")
            return {
                "plan": [],
                "result": f"I encountered an error connecting to my cloud brain: {e}",
            }

    # --- Specialist (MoE) ---
    def specialist_node(self, state: AgentState):
        """
        Uses the MoE model for domain-specific tasks (coding, math, data).
        Model name is read from config.yaml at startup — no per-call disk I/O.
        Falls back to cloud_planning_node if MoE call fails.
        """
        query   = state["query"]
        context = state.get("context", "")

        user_content = ""
        if context:
            user_content += f"Memory Context:\n{context}\n\n"
        user_content += f"Task: {query}"

        try:
            completion = self._nim_client.chat.completions.create(
                model=self._moe_model,
                messages=[
                    {"role": "system", "content": _SPECIALIST_SYSTEM},
                    {"role": "user",   "content": user_content},
                ],
                temperature=0.1,
                max_tokens=2048,
            )
            result = completion.choices[0].message.content
            print(f"[Specialist] Responded using MoE model: {self._moe_model}")
            return {"result": result}

        except Exception as e:
            print(f"[Specialist] MoE model failed ({e}), falling back to cloud planner.")
            return self.cloud_planning_node(state)

    # --- Research ---
    def research_node(self, state: AgentState):
        query = state["query"]
        print(f"[Orchestrator] Delegating to AutoResearcher for: '{query}'")
        res = self.researcher.perform_deep_dive(query)
        return {"result": res, "plan": []}   # Clear plan to avoid re-loop

    # --- Action Execution ---
    def action_execution_node(self, state: AgentState):
        query   = state["query"]
        context = state.get("context", "")
        full_task = f"{context}\n\nTask: {query}".strip() if context else query
        res = self.executor.execute_action(full_task)
        return {"result": res, "plan": []}   # Clear plan to avoid re-loop

    # --- Memory ---
    def memory_mapping_node(self, state: AgentState):
        self.memory.add_to_manifold(
            state["user_id"],
            f"Query: {state['query']} | Result: {state.get('result', '')[:500]}",
        )
        return state

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(self, query: str, user_id: str = "default_user") -> str:
        initial_state: AgentState = {
            "query":   query,
            "user_id": user_id,
            "context": "",
            "route":   "",
            "plan":    [],
            "actions": [],
            "result":  "",
            "errors":  [],
        }
        final_state = self.graph.invoke(initial_state)
        return final_state["result"]
