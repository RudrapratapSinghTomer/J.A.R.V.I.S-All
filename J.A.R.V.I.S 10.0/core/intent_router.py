import os
import json
import re
from openai import OpenAI
from typing import Dict, Optional

class SemanticIntentRouter:
    """
    Semantic Intent Router and Sequence Tracker.
    Classifies user queries into 5 core intents and resolves vague terms
    (e.g., 'fix it', 'retry') relative to the active episodic workflow state.
    """
    def __init__(self, llm_client: Optional[OpenAI] = None, model: str = "meta/llama-3.3-70b-instruct"):
        self.llm_client = llm_client
        self.model = model

    def route_intent(self, query: str, workflow_context: Optional[dict] = None) -> dict:
        """
        Routes the user query to its semantic intent.
        Resolves vague references if context is active.
        """
        if workflow_context is None:
            workflow_context = {
                "last_query": None,
                "last_action": None,
                "last_error": None,
                "active_topic": None
            }

        # 1. Try LLM-driven Classification & Resolution
        if self.llm_client:
            try:
                result = self._route_with_llm(query, workflow_context)
                if result:
                    return result
            except Exception as e:
                print(f"[IntentRouter Warning] LLM intent classification failed: {e}. Falling back to deterministic heuristics.")

        # 2. Offline Fallback Heuristics
        return self._route_with_heuristics(query, workflow_context)

    def _route_with_llm(self, query: str, workflow_context: dict) -> Optional[dict]:
        """Classifies intent and resolves pronouns using the LLM."""
        prompt = (
            "You are the J.A.R.V.I.S 10.0 Semantic Intent Router and Workflow Sequence Classifier.\n"
            "Your job is to analyze the User Query and classify its intent into one of these 5 categories:\n"
            "1. 'MEMORY_STORE': The user explicitly asks you to remember, store, or save a personal preference, setting, or fact (e.g., 'remember that my favorite theme is Cobalt Neon Blue').\n"
            "2. 'DIRECT_ACTION': Simple, direct system commands like opening a web page/URL, running a basic host application (notepad, calc), playing media on YouTube, or capturing/analyzing a webcam image (e.g., 'open notepad', 'play Beethoven', 'look at me', 'take a webcam capture').\n"
            "3. 'WEB_SEARCH': Asking to search the web, DuckDuckGo, or look up information online (e.g., 'search the web for python 3.11 features').\n"
            "4. 'GENERAL_QUERY': Conversational greetings, simple questions, direct chat, system status inquiries, or standard explanations that do NOT require plans or terminal commands (e.g., 'hello', 'how are you doing?', 'status check', 'who are you?').\n"
            "5. 'COMPLEX_PLAN': Complex developer tasks, programming, writing or modifying code, running file edits, executing commands in sandbox, or multi-step execution tasks requiring plans and validating loops (e.g., 'write a prime script and run it').\n\n"
            "### SEQUENCE TRACKING & VAGUE TERM RESOLUTION:\n"
            "If the user query is vague, short, or references a previous topic via pronouns (e.g., 'fix it', 'retry', 'run it again', 'do it', 'show me'), you MUST resolve these terms using the Workflow Context below to reconstruct the full, explicit query intended by the user.\n\n"
            f"WORKFLOW CONTEXT:\n{json.dumps(workflow_context, indent=2)}\n\n"
            f"USER QUERY: {query}\n\n"
            "Respond in JSON format with three fields:\n"
            "- 'intent': One of the 5 category strings above.\n"
            "- 'resolved_query': The reconstructed explicit query (use original query if no vague references exist).\n"
            "- 'reason': A brief explanation of the intent routing and any vague pronoun resolution applied.\n"
            "Ensure the response is valid JSON and nothing else."
        )

        try:
            completion = self.llm_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            data = json.loads(completion.choices[0].message.content)
            # Ensure return dict has uppercase keys and appropriate shape
            intent = data.get("intent", "GENERAL_QUERY").upper()
            resolved = data.get("resolved_query", query)
            reason = data.get("reason", "LLM Routed.")
            
            # Map standard intent strings defensively
            valid_intents = {"MEMORY_STORE", "DIRECT_ACTION", "WEB_SEARCH", "GENERAL_QUERY", "COMPLEX_PLAN"}
            if intent not in valid_intents:
                intent = "COMPLEX_PLAN" if "plan" in intent.lower() else "GENERAL_QUERY"

            return {
                "intent": intent,
                "resolved_query": resolved,
                "reason": reason
            }
        except Exception as e:
            # Retry without response_format in case the API doesn't support it
            if "response_format" in str(e).lower() or "unsupported" in str(e).lower():
                completion = self.llm_client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0
                )
                data = json.loads(completion.choices[0].message.content)
                intent = data.get("intent", "GENERAL_QUERY").upper()
                resolved = data.get("resolved_query", query)
                reason = data.get("reason", "LLM Routed.")
                return {
                    "intent": intent,
                    "resolved_query": resolved,
                    "reason": reason
                }
            raise e

    def _route_with_heuristics(self, query: str, workflow_context: dict) -> dict:
        """Deterministic offline fallback heuristics for routing and pronoun resolution."""
        cleaned = query.strip().lower()
        normalized = cleaned.replace("j.a.r.v.i.s", "jarvis")
        normalized = re.sub(r"[^\w\s]", " ", normalized)
        normalized = " ".join(normalized.split())

        # 1. Vague pronoun/continuation term resolution
        vague_patterns = [
            r"^fix it$", r"^retry$", r"^run it again$", r"^do it$", r"^execute it$",
            r"^try again$", r"^fix the error$", r"^re-run$", r"^run it$", r"^retry it$"
        ]
        is_vague = any(re.match(pat, cleaned) for pat in vague_patterns)
        resolved_query = query
        resolution_reason = "No sequence tracking resolution needed."

        if is_vague and workflow_context.get("last_query"):
            last_q = workflow_context["last_query"]
            last_err = workflow_context.get("last_error")
            if "fix" in cleaned and last_err:
                resolved_query = f"Fix the error '{last_err}' in: {last_q}"
                resolution_reason = f"Resolved vague query '{query}' to last error and task."
            else:
                resolved_query = last_q
                resolution_reason = f"Resolved vague query '{query}' to last query."

        # Re-clean resolved query for heuristic classification
        cleaned_res = resolved_query.strip().lower()
        normalized_res = cleaned_res.replace("j.a.r.v.i.s", "jarvis")
        normalized_res = re.sub(r"[^\w\s]", " ", normalized_res)
        normalized_res = " ".join(normalized_res.split())

        # 2. Heuristic classification
        # Complex planner loop keywords (checked first to prevent direct action/search hijacking)
        developer_keywords = {
            "update", "create", "write", "git", "commit", "push", "modify",
            "implement", "delete", "remove", "install", "build", "test",
            "rebuild", "fix", "debug", "compile", "deploy", "readme"
        }
        words = set(re.findall(r"\b\w+\b", normalized_res))
        if any(kw in words for kw in developer_keywords):
            return {
                "intent": "COMPLEX_PLAN",
                "resolved_query": resolved_query,
                "reason": f"Routed to complex planner via developer keyword detection. {resolution_reason}"
            }

        # Memory Ingest
        memory_prefixes = ["remember that", "remember my", "remember this fact", "store fact", "i want you to remember that"]
        if any(cleaned_res.startswith(pref) for pref in memory_prefixes):
            return {
                "intent": "MEMORY_STORE",
                "resolved_query": resolved_query,
                "reason": f"Routed via memory prefix heuristic. {resolution_reason}"
            }

        # Direct Actions
        simple_actions = ["open ", "play ", "go to ", "navigate to ", "run "]
        vision_keywords = ["webcam", "web cam", "take a picture", "look at me", "identify objects", "camera capture"]
        if any(cleaned_res.startswith(act) for act in simple_actions) or any(kw in cleaned_res for kw in vision_keywords):
            return {
                "intent": "DIRECT_ACTION",
                "resolved_query": resolved_query,
                "reason": f"Routed via direct action keyword heuristic. {resolution_reason}"
            }

        # Web Search
        search_prefixes = ["search ", "google ", "duckduckgo ", "search the web"]
        if any(cleaned_res.startswith(pref) for pref in search_prefixes):
            return {
                "intent": "WEB_SEARCH",
                "resolved_query": resolved_query,
                "reason": f"Routed via search prefix heuristic. {resolution_reason}"
            }

        # General Conversation / Simple queries
        greetings = {
            "hi", "hello", "hey", "greetings", "good morning", "good afternoon", "good evening",
            "howdy", "yo", "hi jarvis", "hello jarvis", "hey jarvis", "jarvis"
        }
        simple_inquiries = {
            "who are you", "what are you", "who am i", "what is my name",
            "how are you", "are you online", "are you there", "status", "system check",
            "help", "info", "ping", "test", "how are you doing"
        }
        if normalized_res in greetings or any(q in normalized_res for q in simple_inquiries):
            return {
                "intent": "GENERAL_QUERY",
                "resolved_query": resolved_query,
                "reason": f"Routed via simple conversational heuristics. {resolution_reason}"
            }

        # Default fallback
        return {
            "intent": "GENERAL_QUERY",
            "resolved_query": resolved_query,
            "reason": f"Default fallback to conversational query. {resolution_reason}"
        }
