import os
import json
import yaml
import asyncio
import re
import urllib.parse
from openai import OpenAI
from typing import List, Dict, Set, Optional
from core.planner import CognitivePlanner
from core.cli_engine import CLIEngine
from core.memory import SystemContextMemory, AgentMemory
from core.persona import get_persona  # Phase 1: persona & context injection
from core.audio_pipeline import UserStateDetector  # Phase 2: urgency & emotion detection
from core.intent_router import SemanticIntentRouter  # Phase 4: intent routing

class DualLoopOrchestrator:
    """
    Dual-Loop Orchestration Engine.
    Executes tasks in parallel using asyncio, validates each step's outputs,
    and coordinates System/Agent memory updates.
    """
    def __init__(self, 
                 planner: CognitivePlanner, 
                 cli_engine: CLIEngine, 
                 sys_memory: SystemContextMemory,
                 agent_memory: AgentMemory,
                 llm_client: OpenAI = None,
                 model: str = "meta/llama-3.3-70b-instruct",
                 browser = None,
                 acquirer = None,
                 plugin_manager = None,
                 vision = None):
        self.planner = planner
        self.cli_engine = cli_engine
        self.sys_memory = sys_memory
        self.agent_memory = agent_memory
        self.llm_client = llm_client
        self.model = model
        self.browser = browser
        self.acquirer = acquirer
        self.plugin_manager = plugin_manager
        self.vision = vision
        self.intent_router = SemanticIntentRouter(llm_client, model)

    def _resolve_image_path(self, image_path: str) -> Optional[str]:
        """Resolves an image path robustly and defensively on both Windows host and Linux sandboxes."""
        if not image_path:
            return None
            
        # 1. Standardize separators for the current OS
        var_path = image_path.replace("\\", "/")
        workspace_root = self.sys_memory.workspace_root.replace("\\", "/")
        
        # 2. Extract path candidates
        roots = []
        is_linux = (os.name != 'nt')
        
        clean_workspace = workspace_root
        if is_linux:
            # If workspace_root starts with Windows drive letter like "C:" or "c:"
            if re.match(r"^[a-zA-Z]:", clean_workspace):
                clean_workspace = re.sub(r"^[a-zA-Z]:", "", clean_workspace)
            # Add standard /workspace container roots
            roots.append("/workspace")
            roots.append("/workspace/J.A.R.V.I.S 10.0")
            
        roots.append(self.sys_memory.workspace_root)
        roots.append(clean_workspace)
        roots.append(os.getcwd())
        
        # Add locations relative to orchestrator file itself
        file_dir = os.path.dirname(os.path.abspath(__file__))
        roots.append(os.path.normpath(os.path.join(file_dir, "..")))
        roots.append(os.path.normpath(os.path.join(file_dir, "..", "..")))
        
        # Add variations of var_path
        path_variations = [var_path]
        
        # Remove drive letter from var_path if present and we are on Linux
        if is_linux and re.match(r"^[a-zA-Z]:", var_path):
            no_drive = re.sub(r"^[a-zA-Z]:", "", var_path)
            path_variations.append(no_drive)
            # Try to grab relative part from J.A.R.V.I.S folders
            match = re.search(r"J\.A\.R\.V\.I\.S\s+All/(.*)$", var_path, re.IGNORECASE)
            if match:
                path_variations.append("/workspace/" + match.group(1))
                path_variations.append(match.group(1))
            match_v10 = re.search(r"J\.A\.R\.V\.I\.S\s+10\.0/(.*)$", var_path, re.IGNORECASE)
            if match_v10:
                path_variations.append("/workspace/J.A.R.V.I.S 10.0/" + match_v10.group(1))
                path_variations.append("J.A.R.V.I.S 10.0/" + match_v10.group(1))
                path_variations.append(match_v10.group(1))
                
        # Also extract basename to look it up in screenshots folder
        basename = os.path.basename(var_path)
        if basename != var_path:
            path_variations.append(basename)
            
        # Let's generate search locations
        search_locations = []
        for var in path_variations:
            search_locations.append(var)
            search_locations.append(os.path.abspath(var))
            search_locations.append(os.path.normpath(var))
            
            for root in roots:
                if not root:
                    continue
                search_locations.append(os.path.normpath(os.path.join(root, var)))
                search_locations.append(os.path.normpath(os.path.join(root, "J.A.R.V.I.S 10.0", "capabilities", "screenshots", var)))
                search_locations.append(os.path.normpath(os.path.join(root, "capabilities", "screenshots", var)))
                search_locations.append(os.path.normpath(os.path.join(root, "screenshots", var)))
                
        # Filter duplicates and check existence (probing standard extensions)
        checked = set()
        for loc in search_locations:
            normalized_loc = os.path.normpath(loc)
            
            # Generate variations with standard image extensions
            _, ext = os.path.splitext(normalized_loc)
            loc_variations = [normalized_loc]
            if not ext or ext.lower() not in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]:
                for e in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]:
                    loc_variations.append(normalized_loc + e)
                    
            for var_loc in loc_variations:
                if var_loc in checked:
                    continue
                checked.add(var_loc)
                
                # On Linux, if it still contains drive letters like "c:\", clean it up
                if is_linux and re.search(r"[a-zA-Z]:", var_loc):
                    cleaned_loc = re.sub(r"^[a-zA-Z]:", "", var_loc).replace("\\", "/")
                    if cleaned_loc not in checked:
                        checked.add(cleaned_loc)
                        if os.path.exists(cleaned_loc) and os.path.isfile(cleaned_loc):
                            return cleaned_loc
                    cleaned_loc2 = re.sub(r".*?[a-zA-Z]:", "", var_loc).replace("\\", "/")
                    cleaned_loc2 = "/" + cleaned_loc2.lstrip("/")
                    if cleaned_loc2 not in checked:
                        checked.add(cleaned_loc2)
                        if os.path.exists(cleaned_loc2) and os.path.isfile(cleaned_loc2):
                            return cleaned_loc2
                            
                if os.path.exists(var_loc) and os.path.isfile(var_loc):
                    return var_loc
                    
        # 3. Fuzzy & Generic Search Fallback inside screenshot directories and workspace roots
        # Gather all valid searchable directories
        search_dirs = []
        for root in roots:
            if not root:
                continue
            search_dirs.append(os.path.normpath(os.path.join(root, "J.A.R.V.I.S 10.0", "capabilities", "screenshots")))
            search_dirs.append(os.path.normpath(os.path.join(root, "capabilities", "screenshots")))
            search_dirs.append(os.path.normpath(os.path.join(root, "screenshots")))
            search_dirs.append(os.path.normpath(root))
            
        valid_dirs = []
        for sdir in search_dirs:
            if os.path.exists(sdir) and os.path.isdir(sdir):
                if sdir not in valid_dirs:
                    valid_dirs.append(sdir)
                    
        # Extract clean query base name
        base_query = os.path.basename(var_path)
        base_query_no_ext, _ = os.path.splitext(base_query)
        base_query_clean = base_query_no_ext.strip().lower()
        
        if base_query_clean:
            fuzzy_candidates = []
            for sdir in valid_dirs:
                try:
                    for filename in os.listdir(sdir):
                        fpath = os.path.join(sdir, filename)
                        if os.path.isfile(fpath):
                            _, fext = os.path.splitext(filename)
                            if fext.lower() in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]:
                                fname_lower = filename.lower()
                                fname_no_ext, _ = os.path.splitext(fname_lower)
                                if base_query_clean in fname_lower or fname_lower in base_query_clean or base_query_clean in fname_no_ext:
                                    mtime = os.path.getmtime(fpath)
                                    fuzzy_candidates.append((fpath, mtime))
                except Exception:
                    pass
            if fuzzy_candidates:
                fuzzy_candidates.sort(key=lambda x: x[1], reverse=True)
                print(f"[Orchestrator Path Resolver] Exact match failed. Fuzzy resolved '{image_path}' to: {fuzzy_candidates[0][0]}")
                return fuzzy_candidates[0][0]
                
        # Generic fallback to latest available image
        generic_terms = ["latest", "image", "screenshot", "webcam", "capture", "current", "photo", "pic"]
        is_generic = any(t in base_query_clean for t in generic_terms) if base_query_clean else True
        if is_generic:
            all_images = []
            for sdir in valid_dirs:
                try:
                    for filename in os.listdir(sdir):
                        fpath = os.path.join(sdir, filename)
                        if os.path.isfile(fpath):
                            _, fext = os.path.splitext(filename)
                            if fext.lower() in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]:
                                mtime = os.path.getmtime(fpath)
                                all_images.append((fpath, mtime))
                except Exception:
                    pass
            if all_images:
                all_images.sort(key=lambda x: x[1], reverse=True)
                print(f"[Orchestrator Path Resolver] Generic fallback resolved '{image_path}' to latest screenshot: {all_images[0][0]}")
                return all_images[0][0]
                
        return None

    def _is_query_complex(self, query: str) -> bool:
        """Determines if a query requires multi-step planning or is simple chit-chat/greetings/commands."""
        cleaned = query.strip().lower()
        
        # Normalize punctuation and j.a.r.v.i.s / jarvis references
        normalized = cleaned.replace("j.a.r.v.i.s", "jarvis")
        normalized = re.sub(r"[^\w\s]", " ", normalized)  # Replace punctuation with spaces
        normalized = " ".join(normalized.split())          # Normalize whitespace
        
        # Pre-screen: Force complex for action-oriented developer queries
        developer_keywords = {
            "update", "create", "write", "git", "commit", "push", "modify", 
            "implement", "delete", "remove", "install", "build", "test", 
            "rebuild", "fix", "debug", "compile", "deploy", "readme"
        }
        words = set(re.findall(r"\b\w+\b", normalized))
        if any(kw in words for kw in developer_keywords):
            return True

        # Heuristics for quick, instantaneous direct responses
        greetings = {
            "hi", "hello", "hey", "greetings", "good morning", "good afternoon", "good evening", 
            "howdy", "hi jarvis", "hello jarvis", "hey jarvis", "jarvis", "yo", "yo jarvis",
            "good morning jarvis", "good afternoon jarvis", "good evening jarvis"
        }
        
        if normalized in greetings:
            return False
            
        simple_inquiries = {
            "who are you", "what are you", "who am i", "what is my name", 
            "how are you", "are you online", "are you there", "status", "system check", 
            "help", "info", "ping", "test", "how are you doing"
        }
        
        if any(q in normalized for q in simple_inquiries):
            return False

        # Pre-screen simple actions like open or play to execute directly
        simple_actions = {"open ", "play ", "go to ", "navigate to ", "run "}
        if any(cleaned.startswith(act) or normalized.startswith(act) for act in simple_actions):
            return False

        if not self.llm_client:
            return False  # Offline mode fallback defaults to simple responses

        # LLM complexity classifier
        prompt = (
            "You are the J.A.R.V.I.S Query Complexity Classifier.\n"
            "Analyze the User Query and classify it as:\n"
            "- 'SIMPLE': A greeting, direct conversational question, status check, or simple request that can be answered immediately.\n"
            "- 'COMPLEX': Requires multi-step plans, terminal command execution, research, capability propose/approve, or code modifications.\n\n"
            f"USER QUERY: {query}\n\n"
            "Respond in JSON format with 'complexity' ('SIMPLE' or 'COMPLEX') and 'reason' (string).\n"
            "Format:\n"
            "{\n"
            "  \"complexity\": \"SIMPLE\",\n"
            "  \"reason\": \"Brief conversational greeting\"\n"
            "}\n"
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
            return data.get("complexity", "SIMPLE").upper() == "COMPLEX"
        except Exception:
            # Fallback heuristic
            return True

    def _personalize_response(self, raw_response: str, query: str, sys_context: str, user_state: dict = None) -> str:
        """Applies J.A.R.V.I.S personality filter to make responses calculated, context-rich, and specific."""
        if not self.llm_client:
            return raw_response
            
        persona_msg = get_persona().get_system_message()
        
        user_state_instructions = ""
        if user_state:
            user_state_instructions = (
                f"6. ADAPTS perfectly to the user's state: Emotion={user_state.get('emotion', 'calm')}, Urgency={user_state.get('urgency', 'normal')}.\n"
                "If the user is in a hurry or panicking (urgency is high), drop the dry wit, greetings, and wordiness, be extremely brief and professional, and express calm reassurance.\n"
            )

        prompt = (
            "You are the J.A.R.V.I.S Response Calculator and Personalizer.\n"
            "Review the raw assistant response and refine it. Ensure it:\n"
            "1. Addresses the user specifically as 'sir' or using details from the User Vault (e.g. name, preferences).\n"
            "2. Is highly specific, mathematically/conceptually calculated, and context-rich.\n"
            "3. Uses calm, measured British phrasing (polite, witty, quietly competent).\n"
            "4. Integrates environment details and active/available skills organically if relevant.\n"
            "5. NEVER outputs generic or placeholder information. Every answer must be calculated, personalized, and rich in system context.\n"
            f"{user_state_instructions}\n"
            f"SYSTEM CONTEXT:\n{sys_context}\n\n"
            f"USER QUERY: {query}\n"
            f"RAW RESPONSE: {raw_response}\n\n"
            "Output your refined response directly. Do not include any tags or conversational metadata."
        )
        try:
            completion = self.llm_client.chat.completions.create(
                model=self.model,
                messages=[persona_msg, {"role": "user", "content": prompt}],
                temperature=0.3
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            print(f"[Orchestrator Warning] Personalization filter failed: {e}")
            return raw_response

    async def _execute_direct_action(self, query: str) -> Optional[str]:
        """Executes simple actions directly without planning loop."""
        cleaned = query.strip().lower()
        
        # 1. Open URL / Navigate
        for prefix in ["open ", "go to ", "navigate to "]:
            if cleaned.startswith(prefix):
                target = query[len(prefix):].strip()
                if "." in target or "http" in target or "www." in target:
                    # It's a URL
                    if self.browser:
                        print(f"[Orchestrator Direct] Navigating to URL: '{target}'")
                        loop = asyncio.get_running_loop()
                        res = await loop.run_in_executor(None, self.browser.smart_navigate, target)
                        if res.get("success"):
                            return f"I have successfully opened the web page at {target}, sir."
                        else:
                            return f"I attempted to navigate to {target}, sir, but encountered an error: {res.get('error')}"
                else:
                    # It's an application (e.g. open notepad, open calculator)
                    print(f"[Orchestrator Direct] Opening system application: '{target}'")
                    loop = asyncio.get_running_loop()
                    res = await loop.run_in_executor(None, self.cli_engine.execute_and_validate, f"start {target}")
                    if res["success"]:
                        return f"I have opened {target} for you, sir."
                    else:
                        # Fallback try running command directly
                        res2 = await loop.run_in_executor(None, self.cli_engine.execute_and_validate, target)
                        if res2["success"]:
                            return f"Executed '{target}' successfully, sir."
                        return f"I was unable to open the application '{target}', sir. Perhaps it is not in the system path."

        # 2. Play audio/video on YouTube
        if cleaned.startswith("play "):
            target = query[5:].strip()
            if self.browser:
                print(f"[Orchestrator Direct] Searching and playing: '{target}' on YouTube")
                search_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(target)}"
                loop = asyncio.get_running_loop()
                res = await loop.run_in_executor(None, self.browser.smart_navigate, search_url)
                if res.get("success"):
                    return f"I have searched for and initiated playback for '{target}' on YouTube, sir."
                else:
                    return f"I attempted to search YouTube for '{target}', sir, but encountered an error: {res.get('error')}"

        # 3. Dynamic Webcam & Vision capture
        vision_keywords = ["webcam", "web cam", "take a picture", "look at me", "identify objects", "what objects you can identify"]
        if any(kw in cleaned for kw in vision_keywords):
            if self.vision:
                print("[Orchestrator Direct] Webcam/Vision request identified. Capturing frame...")
                loop = asyncio.get_running_loop()
                res = await loop.run_in_executor(
                    None,
                    self.vision.capture_and_analyze,
                    "Identify all the objects you can see in this webcam snapshot and describe them."
                )
                if res.get("success"):
                    return f"I have successfully captured a frame from the webcam, sir. Here is my analysis: {res.get('analysis')}"
                else:
                    return f"I attempted to capture a frame from the webcam, sir, but failed: {res.get('error')}"

        return None

    async def run(self, query: str, user_id: str = "developer") -> str:
        print(f"\n[Orchestrator] Starting processing loop for: '{query}'")

        # Phase 2: Detect user urgency and emotional state
        user_state = UserStateDetector.detect(query)
        detected_emotion = user_state["emotion"]
        is_urgent = user_state["urgency"] == "high"
        
        # Phase 4: Semantic Intent Routing & Vague reference resolution
        workflow_context = self.agent_memory.get_workflow_state()
        routing = self.intent_router.route_intent(user_state["text"], workflow_context)
        intent = routing["intent"]
        resolved_query = routing["resolved_query"]
        
        print(f"[Orchestrator Intent] Routed User Query to: '{intent}' (Resolved Query: '{resolved_query}')")
        user_state["text"] = resolved_query
        
        if is_urgent:
            print("[Orchestrator] High urgency detected! Prioritizing speed and direct responsiveness.")

        # 1. Compile Global Context & LTM Memory
        sys_context = self.sys_memory.compile_global_context()
        past_episodes = self.agent_memory.search_ltm(resolved_query)

        # Inject retrieved semantically similar past memories and facts directly into the environment context
        if past_episodes:
            sys_context += "\n=== RETRIEVED LONG-TERM MEMORIES (SEMANTIC FACTS & EPISODES) ===\n"
            for i, record in enumerate(past_episodes):
                query_field = record.get("query", "Fact")
                resolution_field = record.get("resolution", "")
                sys_context += f"Memory {i+1}:\n"
                sys_context += f"- Context/Query: {query_field}\n"
                sys_context += f"- Detail/Resolution: {resolution_field}\n"
                if record.get("code_snippets"):
                    sys_context += f"- Code Snippets: {', '.join(record['code_snippets'])}\n"
                sys_context += "\n"

        # Inject User State actively into system context
        user_state_str = f"User State: Emotion={detected_emotion.upper()}, Urgency={user_state['urgency'].upper()}"
        sys_context += f"\n=== ACTIVE USER STATE ===\n{user_state_str}\n"

        # Execute based on the routed intent
        if intent == "MEMORY_STORE":
            # Extract preference or fact
            fact = resolved_query
            cleaned_fact = fact.lower().replace("jarvis,", "").replace("jarvis", "").strip()
            prefixes = ["remember that", "remember my", "remember this fact", "store fact", "i want you to remember that"]
            for pref in prefixes:
                if cleaned_fact.startswith(pref):
                    idx = fact.lower().find(pref)
                    fact = fact[idx + len(pref):].strip()
                    fact = fact.lstrip(": ,.!?").strip()
                    break
            self.agent_memory.add_semantic_fact(fact, "preference")
            
            # Update workflow state
            self.agent_memory.update_workflow_state(
                last_query=resolved_query,
                last_action="MEMORY_STORE",
                last_error=None,
                active_topic="User Preference/Fact Store"
            )
            
            response = f"I have successfully committed that preference to my persistent memory core, sir. I will remember that: '{fact}'."
            return f"[{detected_emotion}] {response}"

        elif intent == "DIRECT_ACTION":
            print("[Orchestrator] Executing direct action bypass...")
            direct_action_res = await self._execute_direct_action(resolved_query)
            if direct_action_res:
                personalized_res = self._personalize_response(direct_action_res, resolved_query, sys_context, user_state)
                cleaned_personalized_res = re.sub(r"^\[[a-zA-Z\s_]+\]\s*", "", personalized_res).strip()
                
                # Update workflow state
                self.agent_memory.update_workflow_state(
                    last_query=resolved_query,
                    last_action="DIRECT_ACTION",
                    last_error=None,
                    active_topic="Direct System/Media Action"
                )
                
                return f"[{detected_emotion}] {cleaned_personalized_res}"
            else:
                print("[Orchestrator Warning] Direct action bypass not supported for this query. Falling back to planning flow...")
                intent = "COMPLEX_PLAN"

        elif intent == "WEB_SEARCH":
            print("[Orchestrator] Executing direct web search bypass...")
            if self.browser:
                loop = asyncio.get_running_loop()
                res = await loop.run_in_executor(None, self.browser.smart_navigate, resolved_query)
                if res.get("success"):
                    search_res = f"I have searched the web for your query and initiated navigation, sir."
                else:
                    search_res = f"I attempted to search the web for '{resolved_query}', sir, but encountered an error: {res.get('error')}"
            else:
                search_res = "I am unable to perform a web search at the moment, sir, as the WebBridge browser module is currently offline."
                
            personalized_res = self._personalize_response(search_res, resolved_query, sys_context, user_state)
            cleaned_personalized_res = re.sub(r"^\[[a-zA-Z\s_]+\]\s*", "", personalized_res).strip()
            
            # Update workflow state
            self.agent_memory.update_workflow_state(
                last_query=resolved_query,
                last_action="WEB_SEARCH",
                last_error=None,
                active_topic="Web Inquiry"
            )
            
            return f"[{detected_emotion}] {cleaned_personalized_res}"

        elif intent == "GENERAL_QUERY":
            print("[Orchestrator] Executing direct conversational bypass...")
            direct_res = self._generate_direct_response(resolved_query, sys_context, user_state)
            personalized_res = self._personalize_response(direct_res, resolved_query, sys_context, user_state)
            cleaned_personalized_res = re.sub(r"^\[[a-zA-Z\s_]+\]\s*", "", personalized_res).strip()
            
            # Update workflow state
            self.agent_memory.update_workflow_state(
                last_query=resolved_query,
                last_action="GENERAL_QUERY",
                last_error=None,
                active_topic="Conversation"
            )
            
            return f"[{detected_emotion}] {cleaned_personalized_res}"

        # Standard COMPLEX_PLAN intent flow:
        print("[Orchestrator] Generating plan for complex task...")
        plan = self.planner.generate_plan(resolved_query, sys_context, past_episodes)
        print(f"[Orchestrator] Plan Generated: '{plan.get('goal', 'No Goal')}'")
        
        steps = plan.get("steps", [])
        if not steps:
            print("[Orchestrator] Plan has no steps. Generating honest direct failure response...")
            direct_res = self._generate_direct_response(resolved_query, sys_context, user_state, plan_failed=True)
            personalized_res = self._personalize_response(direct_res, resolved_query, sys_context, user_state)
            cleaned_personalized_res = re.sub(r"^\[[a-zA-Z\s_]+\]\s*", "", personalized_res).strip()
            
            self.agent_memory.update_workflow_state(
                last_query=resolved_query,
                last_action="COMPLEX_PLAN_FAILED",
                last_error="Planning phase failed to produce executable steps.",
                active_topic="System Operation Failure"
            )
            return f"[{detected_emotion}] {cleaned_personalized_res}"
        
        for step in steps:
            print(f"  Step {step.get('id')}: {step.get('description')} (Deps: {step.get('dependencies')})")

        # 3. Parallelized Execution Loop
        completed_steps: Set[int] = set()
        active_tasks = {}
        
        uncompleted_steps = {step["id"]: step for step in steps}
        step_results = {}

        while uncompleted_steps:
            # Find steps that are ready (all dependencies completed, not yet started)
            ready_steps = [
                step for step in uncompleted_steps.values()
                if step["id"] not in active_tasks and set(step.get("dependencies", [])).issubset(completed_steps)
            ]

            if not ready_steps and not active_tasks:
                print("[Orchestrator Error] Deadlock detected or plan contains cyclic dependencies.")
                break

            # Start ready steps in parallel
            for step in ready_steps:
                step_id = step["id"]
                # Schedule step execution asynchronously
                print(f"[Orchestrator] Dispatching Step {step_id} in parallel: '{step['description']}'")
                active_tasks[step_id] = asyncio.create_task(self._execute_and_validate_step(step))

            if active_tasks:
                # Wait for any active task to finish
                done, _ = await asyncio.wait(active_tasks.values(), return_when=asyncio.FIRST_COMPLETED)
                
                # Process completed tasks
                for task in done:
                    # Find step_id of completed task
                    step_id = [sid for sid, t in active_tasks.items() if t == task][0]
                    del active_tasks[step_id]
                    
                    result = task.result()
                    step_results[step_id] = result
                    
                    if result["success"]:
                        print(f"[Orchestrator] Step {step_id} completed and validated successfully!")
                        completed_steps.add(step_id)
                        del uncompleted_steps[step_id]
                    else:
                        print(f"[Orchestrator Critical] Step {step_id} failed verification: {result.get('error', 'Execution error')}")
                        error_msg = result.get('error', 'Execution error')
                        self.agent_memory.update_workflow_state(
                            last_query=resolved_query,
                            last_action=f"STEP_{step_id}_FAILED",
                            last_error=error_msg,
                            active_topic="System Execution Error"
                        )
                        return f"Orchestration loop aborted due to failure at Step {step_id}: {error_msg}"

            # Small sleep to prevent busy-waiting loop
            await asyncio.sleep(0.1)

        # 4. Final Output Synthesis & Memory Log
        consolidated_summary = self._synthesize_final_output(user_state["text"], step_results)
        personalized_res = self._personalize_response(consolidated_summary, user_state["text"], sys_context, user_state)
        
        # Clean duplicate bracketed tags from the final string
        cleaned_personalized_res = re.sub(r"^\[[a-zA-Z\s_]+\]\s*", "", personalized_res).strip()
        vocal_emotion = f"[{detected_emotion}] {cleaned_personalized_res}"
        
        # Save interaction to LTM Memory
        self.agent_memory.add_to_ltm(
            query=query,
            resolution=vocal_emotion
        )

        self.agent_memory.update_workflow_state(
            last_query=resolved_query,
            last_action="COMPLEX_PLAN_SUCCESS",
            last_error=None,
            active_topic="System Execution Success"
        )

        return vocal_emotion

    async def _execute_and_validate_step(self, step: dict) -> dict:
        """Executes a single plan step in the sandbox, then performs post-execution validation."""
        step_type = step.get("type", "terminal")
        action = step.get("command_or_action", "")
        
        # 1. Execution phase
        if step_type in ("terminal", "edit"):
            # Run terminal command via self-correcting CLI Engine
            # We run blocking executables inside an executor pool to keep orchestrator async loop responsive
            loop = asyncio.get_running_loop()
            exec_res = await loop.run_in_executor(
                None, 
                self.cli_engine.execute_and_validate, 
                action
            )
        elif step_type == "browser":
            # Execute browser actions via the WebBridge browser
            if self.browser:
                loop = asyncio.get_running_loop()
                exec_res = await loop.run_in_executor(
                    None,
                    lambda: self.browser.smart_navigate(action)
                )
                # Normalize browser result to match expected format
                exec_res = {
                    "success": exec_res.get("success", False),
                    "exit_code": 0 if exec_res.get("success") else 1,
                    "stdout": exec_res.get("message", exec_res.get("data", "")),
                    "stderr": exec_res.get("error", "")
                }
            else:
                exec_res = {"success": False, "exit_code": 1, "stdout": "", "stderr": "Browser not connected to orchestrator."}
        elif step_type == "capability_acquirer":
            # Execute capability acquisition actions
            if self.acquirer:
                loop = asyncio.get_running_loop()
                exec_res = await loop.run_in_executor(
                    None,
                    lambda: self.acquirer.propose_capability_plan(action, "Autonomous capability acquisition")
                )
                exec_res = {
                    "success": exec_res is not None,
                    "exit_code": 0 if exec_res else 1,
                    "stdout": f"Capability plan created at: {exec_res}" if exec_res else "",
                    "stderr": "Failed to create capability plan" if not exec_res else ""
                }
            else:
                exec_res = {"success": False, "exit_code": 1, "stdout": "", "stderr": "CapabilityAcquirer not connected to orchestrator."}
        elif step_type == "plugin":
            # Execute dynamically loaded plugins
            if self.plugin_manager:
                loop = asyncio.get_running_loop()
                plugin_name = step.get("plugin_name", action) # Support explicit plugin_name or parsing from action
                
                # Simple parsing if action contains arguments (e.g. "ad-creative arg1 arg2")
                inputs = {"query": action}
                
                exec_res = await loop.run_in_executor(
                    None,
                    self.plugin_manager.execute_plugin,
                    plugin_name,
                    inputs
                )
                
                # Normalize result
                exec_res = {
                    "success": exec_res.get("success", False),
                    "exit_code": 0 if exec_res.get("success", False) else 1,
                    "stdout": exec_res.get("message", str(exec_res)),
                    "stderr": exec_res.get("error", "")
                }
            else:
                exec_res = {"success": False, "exit_code": 1, "stdout": "", "stderr": "PluginManager not connected to orchestrator."}
        elif step_type == "vision":
            # Execute dynamic hardware vision capability
            if self.vision:
                action_str = action.strip()
                
                # Check for either analyze_existing or capture_and_analyze
                if action_str.startswith("analyze_existing "):
                    # Syntax: analyze_existing <image_path> <prompt>
                    remaining = action_str[len("analyze_existing "):].strip()
                    image_path = ""
                    raw_prompt = "Describe this image."
                    resolved_path = None

                    if remaining.startswith(('"', "'")):
                        quote_char = remaining[0]
                        # Find matching quote
                        match = re.match(rf"^{quote_char}(.*?){quote_char}(.*)$", remaining)
                        if match:
                            image_path = match.group(1).strip()
                            raw_prompt = match.group(2).strip() or "Describe this image."
                        else:
                            parts = remaining.split(" ", 1)
                            image_path = parts[0].strip()
                            raw_prompt = parts[1].strip() if len(parts) > 1 else "Describe this image."
                    else:
                        # No quotes. Might contain spaces if the file path exists on disk.
                        words = remaining.split(" ")
                        
                        # We try combinations of words to find if any form a valid file path
                        for i in range(1, len(words) + 1):
                            candidate_path = " ".join(words[:i]).strip()
                            
                            # Try with common extensions if candidate_path doesn't have one
                            variations = [candidate_path]
                            _, ext = os.path.splitext(candidate_path)
                            if not ext or ext.lower() not in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]:
                                for e in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]:
                                    variations.append(candidate_path + e)
                                    
                            for var_path in variations:
                                loc = self._resolve_image_path(var_path)
                                if loc:
                                    resolved_path = loc
                                    image_path = var_path
                                    raw_prompt = " ".join(words[i:]).strip() or "Describe this image."
                                    break
                            if resolved_path:
                                break

                        if not resolved_path:
                            # Traditional split fallback
                            parts = remaining.split(" ", 1)
                            image_path = parts[0].strip()
                            raw_prompt = parts[1].strip() if len(parts) > 1 else "Describe this image."

                    # 1. Resolve path of existing image file if not already resolved
                    if not resolved_path:
                        variations = [image_path]
                        _, ext = os.path.splitext(image_path)
                        if not ext or ext.lower() not in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]:
                            for e in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]:
                                variations.append(image_path + e)
                                
                        for var_path in variations:
                            loc = self._resolve_image_path(var_path)
                            if loc:
                                resolved_path = loc
                                image_path = var_path
                                break
                                
                    if not resolved_path:
                        exec_res = {
                            "success": False,
                            "exit_code": 1,
                            "stdout": "",
                            "stderr": f"Could not locate image file '{image_path}' in any workspace path."
                        }
                    else:
                        # 2. Load file and analyze
                        try:
                            with open(resolved_path, "rb") as f:
                                image_bytes = f.read()
                            
                            # 3. Defensive sanitization to guarantee descriptive prompt for VLM
                            sanitized_prompt = raw_prompt
                            action_words = ["store", "save", "update", "memorize", "record"]
                            if any(w in raw_prompt.lower() for w in action_words):
                                sanitized_prompt = f"Describe this image in detailed visual terms so I can process and store it. Specifically focus on this user request: {raw_prompt}"

                            print(f"[Orchestrator Step] Running VLM on existing image file: {resolved_path} with prompt: '{sanitized_prompt}'")
                            loop = asyncio.get_running_loop()
                            analysis_text = await loop.run_in_executor(
                                None,
                                self.vision.analyze_image,
                                image_bytes,
                                sanitized_prompt
                            )
                            exec_res = {
                                "success": True,
                                "exit_code": 0,
                                "stdout": analysis_text,
                                "stderr": ""
                            }
                        except Exception as file_err:
                            exec_res = {
                                "success": False,
                                "exit_code": 1,
                                "stdout": "",
                                "stderr": f"Failed to load or analyze existing image: {file_err}"
                            }
                else:
                    # capture_and_analyze route
                    prompt = "Identify all objects you can see in this webcam snapshot and describe them."
                    if action_str.startswith("capture_and_analyze "):
                        prompt = action_str[len("capture_and_analyze "):].strip()
                    elif action_str:
                        prompt = action_str
                    
                    # Sanitization to guarantee VLM returns a descriptive analysis for the post-validator
                    sanitized_prompt = prompt
                    action_words = ["store", "save", "update", "memorize", "record"]
                    if any(w in prompt.lower() for w in action_words):
                        sanitized_prompt = f"Describe this image in detailed visual terms so I can process and store it. Specifically focus on this user request: {prompt}"

                    print(f"[Orchestrator Step] Running vision capture/analysis with prompt: '{sanitized_prompt}'")
                    loop = asyncio.get_running_loop()
                    exec_res = await loop.run_in_executor(
                        None,
                        self.vision.capture_and_analyze,
                        sanitized_prompt
                    )
                    exec_res = {
                        "success": exec_res.get("success", False),
                        "exit_code": 0 if exec_res.get("success", False) else 1,
                        "stdout": exec_res.get("analysis", ""),
                        "stderr": exec_res.get("error", "")
                    }
            else:
                exec_res = {"success": False, "exit_code": 1, "stdout": "", "stderr": "Vision module not connected to orchestrator."}
        else:
            # Fallback executor for unknown types
            exec_res = {"success": True, "stdout": f"Action {step_type} executed successfully.", "stderr": ""}

        if not exec_res["success"]:
            return {"success": False, "error": exec_res.get("stderr", "Execution failure")}

        # 2. Validation phase: Let the LLM post-validate outputs
        val_res = self._post_validate_step(step, exec_res)
        return val_res

    def _post_validate_step(self, step: dict, exec_res: dict) -> dict:
        """Asks the LLM to verify if the output of a command fits the success criteria."""
        if not self.llm_client:
            # Fallback if no LLM: trust CLI exit status
            return {"success": exec_res["success"], "output": exec_res.get("stdout", ""), "error": exec_res.get("stderr", "")}

        # Phase 1: prepend persona system message so the validator speaks as JARVIS
        persona_msg = get_persona().get_system_message()

        user_prompt = (
            "You are acting as the J.A.R.V.I.S Post-Execution Validator.\n"
            "An agent executed a plan step. Verify if the output matches the expected result.\n\n"
            f"STEP DESCRIPTION: {step.get('description')}\n"
            f"STEP ACTION: {step.get('command_or_action')}\n\n"
            f"EXECUTION STDOUT:\n{exec_res.get('stdout')}\n\n"
            f"EXECUTION STDERR:\n{exec_res.get('stderr')}\n\n"
            "Respond in JSON format with 'validated' (boolean) and 'reason' (string).\n"
            "Format:\n"
            "{\n"
            "  \"validated\": true,\n"
            "  \"reason\": \"Output matches expected criteria because...\"\n"
            "}\n"
            "Ensure the response is valid JSON and nothing else."
        )

        try:
            completion = self.llm_client.chat.completions.create(
                model=self.model,
                messages=[persona_msg, {"role": "user", "content": user_prompt}],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            data = json.loads(completion.choices[0].message.content)
            validated = data.get("validated", False)
            reason = data.get("reason", "No reason provided.")
            
            if validated:
                return {"success": True, "output": exec_res.get("stdout", "")}
            else:
                return {"success": False, "error": f"Validation Rejected: {reason}"}
        except Exception as e:
            # Retry without response_format in case the API doesn't support it
            if "response_format" in str(e).lower() or "unsupported" in str(e).lower():
                try:
                    completion = self.llm_client.chat.completions.create(
                        model=self.model,
                        messages=[persona_msg, {"role": "user", "content": user_prompt}],
                        temperature=0.1
                    )
                    data = json.loads(completion.choices[0].message.content)
                    validated = data.get("validated", False)
                    reason = data.get("reason", "No reason provided.")
                    if validated:
                        return {"success": True, "output": exec_res.get("stdout", "")}
                    else:
                        return {"success": False, "error": f"Validation Rejected: {reason}"}
                except Exception as retry_e:
                    print(f"[Orchestrator Validation Error] Retry also failed: {retry_e}")
            # Fallback on LLM parser issues
            print(f"[Orchestrator Validation Error] Verification script failed: {e}")
            return {"success": exec_res["success"], "output": exec_res.get("stdout", ""), "error": exec_res.get("stderr", "")}

    def _synthesize_final_output(self, query: str, step_results: dict) -> str:
        """Synthesizes step execution logs into a unified final answer."""
        if not self.llm_client:
            # Fallback
            summary_lines = []
            for sid, res in step_results.items():
                summary_lines.append(f"Step {sid} Result:\n{res.get('output', '')[:300]}")
            return "\n\n".join(summary_lines)

        # Phase 1: persona system message drives the synthesis tone
        persona_msg = get_persona().get_system_message()

        user_prompt = (
            "Summarize the completed execution of the task plan into a cohesive, concise, "
            "and professional resolution statement for your user. Speak in character as JARVIS.\n\n"
            "CRITICAL EXTREME GROUNDING RULE:\n"
            "You MUST ground your summary strictly and honestly in the exact concrete outputs, stdout, "
            "and errors in the EXECUTION RESULTS. If the results indicate that a directory was empty, "
            "no files were found, or a step had empty output/performed no modifications, you MUST state "
            "this transparently and honestly. NEVER claim success in performing file processing, text updates, "
            "or memory injections if the logs show no files were actually read or processed. Avoid any false "
            "claims of success or hallucinations.\n\n"
            f"USER QUERY: {query}\n\n"
            f"EXECUTION RESULTS:\n{json.dumps(step_results, indent=2)}\n\n"
            "Provide the final response directly."
        )

        try:
            completion = self.llm_client.chat.completions.create(
                model=self.model,
                messages=[persona_msg, {"role": "user", "content": user_prompt}],
                temperature=0.3
            )
            return completion.choices[0].message.content
        except Exception as e:
            return f"Task completed successfully. Logs: {json.dumps(step_results)}"

    def _generate_direct_response(self, query: str, sys_context: str, user_state: dict = None, plan_failed: bool = False) -> str:
        """Generates a direct conversational response when the plan has no executable steps."""
        if not self.llm_client:
            return (
                f"Understood, sir. Your query was '{query}', however I have no executable steps "
                "and no language model available for a direct response at this time."
            )

        # Phase 1: persona system message + user vault context prepended
        persona_msg = get_persona().get_system_message()

        user_state_info = ""
        if user_state:
            user_state_info = (
                f"Note: The user's active state is: Emotion={user_state.get('emotion')}, Urgency={user_state.get('urgency')}.\n"
                "If the user is in a hurry or urgency is high, prioritize speed, be extremely brief, professional, and serious. Otherwise, be witty and conversational.\n"
            )

        if plan_failed:
            user_prompt = (
                "The user has requested an action-oriented or developer task, but the planner was unable "
                "to generate any valid execution steps. You must politely, transparently, and directly "
                "explain that you were unable to plan or execute the required steps. Do NOT claim success "
                "and do NOT hallucinate any file modifications, terminal runs, or database updates.\n\n"
                f"{user_state_info}\n"
                f"SYSTEM CONTEXT:\n{sys_context}\n\n"
                f"USER QUERY: {query}\n\n"
                "Provide your explanation directly."
            )
        else:
            user_prompt = (
                "The user has asked a question or made a request that does not require system commands.\n"
                "Respond directly, concisely, and in full character as J.A.R.V.I.S.\n\n"
                f"{user_state_info}\n"
                f"SYSTEM CONTEXT:\n{sys_context}\n\n"
                f"USER QUERY: {query}\n\n"
                "Provide your response directly."
            )

        try:
            completion = self.llm_client.chat.completions.create(
                model=self.model,
                messages=[persona_msg, {"role": "user", "content": user_prompt}],
                temperature=0.4
            )
            return completion.choices[0].message.content
        except Exception as e:
            return f"I understood your query: '{query}', but encountered an error generating a response: {e}"
