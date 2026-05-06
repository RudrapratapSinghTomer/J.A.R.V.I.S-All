from typing import TypedDict, Annotated, List, Any
from langgraph.graph import StateGraph, END


class AgentState(TypedDict):
    query: str
    user_id: str
    context: str
    route: str
    plan: List[str]
    actions: List[dict]
    result: str
    errors: List[str]


class Orchestrator:
    def __init__(self, router, mhc_memory, researcher, executor):
        self.router = router
        self.memory = mhc_memory
        self.researcher = researcher
        self.executor = executor
        self.graph = self._build_graph()

    def _build_graph(self):
        workflow = StateGraph(AgentState)

        # Nodes
        workflow.add_node("ingestion", self.ingestion_node)
        workflow.add_node("routing", self.routing_node)
        workflow.add_node("local_slm_execution", self.local_slm_node)
        workflow.add_node("cloud_planning", self.cloud_planning_node)
        workflow.add_node("research", self.research_node)
        workflow.add_node("action_execution", self.action_execution_node)
        workflow.add_node("memory_mapping", self.memory_mapping_node)

        # Edges
        workflow.set_entry_point("ingestion")
        workflow.add_edge("ingestion", "routing")

        # Conditional edge based on routing
        workflow.add_conditional_edges(
            "routing",
            lambda x: x["route"],
            {"OLLAMA": "local_slm_execution", "NVIDIA_NIM": "cloud_planning"},
        )

        # From local execution directly to memory mapping
        workflow.add_edge("local_slm_execution", "memory_mapping")

        # Cloud planning conditional edges
        workflow.add_conditional_edges(
            "cloud_planning",
            self.route_after_plan,
            {
                "research": "research",
                "action": "action_execution",
                "finish": "memory_mapping",
            },
        )

        workflow.add_edge("research", "cloud_planning")  # Loop back to planner
        workflow.add_edge("action_execution", "cloud_planning")  # Loop back to planner

        workflow.add_edge("memory_mapping", END)

        return workflow.compile()

    # --- Node Implementations ---
    def ingestion_node(self, state: AgentState):
        query = state["query"]
        user_id = state.get("user_id", "default_user")
        context = self.memory.get_context(user_id, query)
        return {"context": context, "user_id": user_id}

    def routing_node(self, state: AgentState):
        route = self.router.route(state["query"])
        return {"route": route}

    def local_slm_node(self, state: AgentState):
        # Actual Ollama call for simple response
        query = state["query"]
        context = state.get("context", "")

        prompt = f"Context: {context}\n\nUser: {query}\n\nAssistant:"

        try:
            from core.router import OLLAMA_URL, SLM_MODEL
            import requests

            # Using /generate endpoint
            response = requests.post(
                f"{OLLAMA_URL}/generate",
                json={"model": SLM_MODEL, "prompt": prompt, "stream": False},
                timeout=15,
            )
            response.raise_for_status()
            result = response.json().get(
                "response", "I encountered an error processing your request locally."
            )
        except Exception as e:
            print(f"[Orchestrator] Local SLM Error: {e}")
            result = f"Local SLM handled this simple query: {query}. (Ollama connection failed)"

        return {"result": result}

    def cloud_planning_node(self, state: AgentState):
        # NVIDIA NIM Cloud call for deep reasoning and planning
        query = state["query"]
        context = state.get("context", "")

        from openai import OpenAI
        import os

        client = OpenAI(
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=os.getenv("NVIDIA_API_KEY"),
        )

        model = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct")

        messages = [
            {
                "role": "system",
                "content": "You are JARVIS, a sophisticated AI assistant. Generate a plan and a response.",
            },
            {"role": "user", "content": f"Context: {context}\n\nQuery: {query}"},
        ]

        try:
            completion = client.chat.completions.create(
                model=model, messages=messages, temperature=0.2, max_tokens=1024
            )
            response_text = completion.choices[0].message.content

            # Simplistic planning logic based on the response or query
            plan = []
            if "research" in query.lower() or "find" in query.lower():
                plan = ["research"]
            elif any(k in query.lower() for k in ["write", "create", "execute", "run"]):
                plan = ["action"]

            return {"plan": plan, "result": response_text}
        except Exception as e:
            print(f"[Orchestrator] Cloud Model Error: {e}")
            return {
                "plan": [],
                "result": f"I encountered an error connecting to my cloud brain: {e}",
            }

    def route_after_plan(self, state: AgentState):
        plan = state.get("plan", [])
        if not plan:
            return "finish"
        # Take the next step in the plan
        next_step = plan.pop(0)
        return next_step

    def research_node(self, state: AgentState):
        query = state["query"]
        # In a real impl, pass the specific sub-query from the plan
        res = self.researcher.perform_deep_dive(query)
        return {
            "result": state.get("result", "") + "\nResearch: " + res,
            "plan": state.get("plan", []),
        }

    def action_execution_node(self, state: AgentState):
        query = state["query"]
        # Generate and execute script
        res = self.executor.execute_action(query)
        return {
            "result": state.get("result", "") + "\nAction: " + res,
            "plan": state.get("plan", []),
        }

    def memory_mapping_node(self, state: AgentState):
        self.memory.add_to_manifold(
            state["user_id"],
            f"Query: {state['query']} | Result: {state.get('result', '')}",
        )
        return state

    def run(self, query: str, user_id: str = "default_user"):
        initial_state = {
            "query": query,
            "user_id": user_id,
            "context": "",
            "route": "",
            "plan": [],
            "actions": [],
            "result": "",
            "errors": [],
        }
        final_state = self.graph.invoke(initial_state)
        return final_state["result"]
