import os
import json
import re
from datetime import datetime
from typing import List, Dict, Optional
from core.config_loader import load_config

# Load config
_CFG = load_config()


CAP_CFG = _CFG.get("capabilities", {})
REGISTRY_FILE = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", CAP_CFG.get("registry_file", "capabilities/registry.json")))

class SystemContextMemory:
    """
    High-level System Context Memory.
    Monitors workspace path health, active files, dynamic capabilities registry,
    and returns a structured global environment context to inject into LLMs.
    """
    def __init__(self, workspace_root: str, sandbox = None):
        self.workspace_root = os.path.abspath(workspace_root)
        self.active_documents = []
        self.sandbox = sandbox

    def register_active_document(self, file_path: str):
        """Registers a document currently open by the user or agent."""
        abs_path = os.path.abspath(file_path)
        if abs_path not in self.active_documents:
            self.active_documents.append(abs_path)

    def get_registered_capabilities(self) -> List[dict]:
        """Reads the dynamic capabilities from the registry file."""
        if not os.path.exists(REGISTRY_FILE):
            # Auto-initialize empty registry
            os.makedirs(os.path.dirname(REGISTRY_FILE), exist_ok=True)
            with open(REGISTRY_FILE, "w") as f:
                json.dump({"capabilities": {}}, f, indent=2)
            return []

        try:
            with open(REGISTRY_FILE, "r") as f:
                data = json.load(f)
                return list(data.get("capabilities", {}).values())
        except Exception as e:
            print(f"[Memory Error] Failed to read capability registry: {e}")
            return []

    def compile_global_context(self, sandbox_status: str = "Active") -> str:
        """Assembles all system environmental data into a clean, comprehensive system prompt."""
        capabilities = self.get_registered_capabilities()
        
        # Probe environment if sandbox is provided
        env_caps = None
        if self.sandbox:
            try:
                env_caps = self.sandbox.probe_capabilities()
            except Exception as e:
                print(f"[Memory Error] Failed to probe sandbox capabilities: {e}")

        # Update sandbox status based on actual probe
        if env_caps:
            sandbox_status = f"Active ({env_caps['sandbox_mode']})"
        
        context_parts = [
            "=== J.A.R.V.I.S SYSTEM ENVIRONMENT ===",
            f"Workspace Path: {self.workspace_root}",
            f"Sandbox Execution Status: {sandbox_status}"
        ]

        # Probe Webcam and VLM hardware status dynamically
        webcam_ok = False
        try:
            from core.vision import WebcamCapture
            webcam_ok = WebcamCapture.probe_available()
        except Exception:
            pass

        webcam_str = "Detected & Operational (Hardware is active. Fully available via native 'vision' step type using 'capture_and_analyze <prompt>')" if webcam_ok else "Not Detected (Hardware camera probe failed or OpenCV cv2 not available)"
        vlm_str = "Active & Operational (NVIDIA Cloud meta/llama-3.2-90b-vision-instruct and local Ollama llama3.2-vision:11b)"

        if env_caps:
            context_parts.extend([
                "\n--- SYSTEM CAPABILITIES ---",
                f"- OS Environment: {env_caps.get('guest_os', env_caps.get('host_os', 'Unknown'))}",
                f"- Python Version: {env_caps.get('python_version', 'Unknown')}",
                f"- GPU Support: {'CUDA GPU Available' if env_caps.get('gpu_available') else 'CPU Only'}",
                f"- Pip Available: {env_caps.get('pip_available')}",
                f"- Git Available: {env_caps.get('git_available')}",
                f"- NPM Available: {env_caps.get('npm_available')}",
                f"- Webcam Hardware: {webcam_str}",
                f"- Vision Language Model (VLM): {vlm_str}",
                "\n--- SYSTEM LIMITATIONS & ERROR SAFETY ---"
            ])
            for limit in env_caps.get("limitations", []):
                context_parts.append(f"- {limit}")
            
            # Add strict error pattern guidelines directly to system context
            context_parts.extend([
                "- [CRITICAL] Dependency Installation: ALL pip installations must happen inside the correct sandbox environment. Never leak packages or run commands outside the designated sandbox context.",
                "- [CRITICAL] Execution Sequence: NEVER execute scripts or commands that import external libraries before their pip packages have completed installation. Ensure setup/imports run sequentially."
            ])

        context_parts.append("\n--- ACTIVE PLUGINS / CAPABILITIES ---")

        if not capabilities:
            context_parts.append("No dynamic capabilities installed yet.")
        else:
            for cap in capabilities:
                context_parts.append(
                    f"- {cap.get('name', 'Unknown')} (v{cap.get('version', '1.0')}) "
                    f"- Description: {cap.get('description', '')} "
                    f"[Entrypoint: {cap.get('entrypoint', '')}]"
                )

        # Discover and integrate Antigravity pre-built awesome-skills
        try:
            from core.antigravity_loader import AntigravitySkillLoader
            loader = AntigravitySkillLoader()
            skills_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "external_skills", "antigravity"))
            loader.skills_dir = skills_dir
            skills = loader.discover_available_skills()
            if skills:
                context_parts.append("\n--- AVAILABLE PRE-BUILT AWESOME SKILLS (ANTIGRAVITY) ---")
                context_parts.append("The following pre-compiled skills are available for immediate installation. "
                                     "If the user requests a capability or a task that maps to these skills, recommend and execute installation "
                                     "via 'propose antigravity <skill_name>' and 'approve antigravity <skill_name>'.")
                # Show a curated sample of the first 25 skills to avoid prompt bloat
                for skill_name, skill_data in list(skills.items())[:25]:
                    metadata = skill_data.get("metadata", {})
                    desc = metadata.get("description", "No description available.")
                    if len(desc) > 90:
                        desc = desc[:87] + "..."
                    context_parts.append(f"- {skill_name}: {desc}")
                if len(skills) > 25:
                    context_parts.append(f"- ... and {len(skills) - 25} other pre-built awesome skills are ready to be integrated.")
        except Exception as e:
            context_parts.append(f"\n[Memory Warning] Failed to index Antigravity skills: {e}")

        # Discover and list webcam images & screenshots from capabilities/screenshots directory
        try:
            is_linux = (os.name != 'nt')
            clean_workspace = self.workspace_root
            roots = [self.workspace_root]
            if is_linux:
                roots.append("/workspace")
                roots.append("/workspace/J.A.R.V.I.S 10.0")
                if re.match(r"^[a-zA-Z]:", clean_workspace):
                    cleaned = re.sub(r"^[a-zA-Z]:", "", clean_workspace).replace("\\", "/")
                    roots.append(cleaned)
                    roots.append("/" + cleaned.lstrip("/"))

            screenshots_dirs = []
            for root in roots:
                screenshots_dirs.append(os.path.normpath(os.path.join(root, "J.A.R.V.I.S 10.0", "capabilities", "screenshots")))
                screenshots_dirs.append(os.path.normpath(os.path.join(root, "capabilities", "screenshots")))

            found_images = []
            for sdir in screenshots_dirs:
                if os.path.exists(sdir) and os.path.isdir(sdir):
                    # List all files in the directory
                    files = os.listdir(sdir)
                    for file in files:
                        full_p = os.path.join(sdir, file)
                        if os.path.isfile(full_p):
                            _, ext = os.path.splitext(file)
                            if ext.lower() in [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"]:
                                mtime = os.path.getmtime(full_p)
                                found_images.append((file, mtime, full_p))
            
            # Deduplicate by absolute path, sort by modification time descending
            unique_images = {}
            for file, mtime, full_p in found_images:
                unique_images[os.path.normcase(full_p)] = (file, mtime)
            
            sorted_images = sorted(unique_images.values(), key=lambda x: x[1], reverse=True)
            
            if sorted_images:
                context_parts.append("\n--- CAPTURED WEBCAM IMAGES & SCREENSHOTS ---")
                context_parts.append("You are aware of the following captured images/screenshots. "
                                     "You can analyze or reference any of these using the native 'vision' step: "
                                     "e.g., 'analyze_existing <image_name_or_path> <prompt>'")
                for img_name, _ in sorted_images[:15]:
                    context_parts.append(f"- {img_name}")
        except Exception as e:
            context_parts.append(f"\n[Memory Warning] Failed to index screenshots: {e}")

        if self.active_documents:
            context_parts.append("\n--- ACTIVE/OPEN SYSTEM FILES ---")
            for doc in self.active_documents:
                # Show relative path for readability
                rel_path = os.path.relpath(doc, self.workspace_root)
                context_parts.append(f"- {rel_path}")

        context_parts.append("======================================")
        return "\n".join(context_parts)


class AgentMemory:
    """
    Direct Agent Memory Wrapper.
    Contains sliding-window Short-Term Memory (STM) and local episodic
    Long-Term Memory (LTM / LSTM) saving history to local json files and ChromaDB.
    """
    def __init__(self, agent_name: str, max_stm_turns: int = 10):
        self.agent_name = agent_name
        self.max_stm_turns = max_stm_turns
        self.stm: List[Dict[str, str]] = []
        
        # Determine LTM path inside J.A.R.V.I.S 10.0/memory/
        self.memory_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "memory"))
        os.makedirs(self.memory_dir, exist_ok=True)
        self.ltm_path = os.path.join(self.memory_dir, f"ltm_{self.agent_name.lower()}.json")
        self.state_path = os.path.join(self.memory_dir, f"state_{self.agent_name.lower()}.json")
        
        self.ltm = self._load_ltm()
        self.workflow_state = self._load_workflow_state()
        
        # Initialize local persistent ChromaDB collection
        self.collection = None
        try:
            import chromadb
            chroma_dir = os.path.join(self.memory_dir, "chroma")
            os.makedirs(chroma_dir, exist_ok=True)
            self.chroma_client = chromadb.PersistentClient(path=chroma_dir)
            collection_name = f"ltm_{self.agent_name.lower()}"
            # Ensure name fits ChromaDB's naming guidelines (3-63 chars, alphanumeric/underscore/hyphen, no consecutive periods)
            collection_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', collection_name)
            self.collection = self.chroma_client.get_or_create_collection(name=collection_name)
            print(f"[Memory] Successfully connected to ChromaDB collection: '{collection_name}'")
        except Exception as e:
            print(f"[Memory Warning] ChromaDB initialization failed: {e}. Falling back to JSON-only memory.")

    def _load_ltm(self) -> List[dict]:
        """Loads episodic records from disk."""
        if not os.path.exists(self.ltm_path):
            return []
        try:
            with open(self.ltm_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Memory Error] Failed to load LTM for {self.agent_name}: {e}")
            return []

    def _save_ltm(self):
        """Saves episodic records to disk."""
        try:
            with open(self.ltm_path, "w", encoding="utf-8") as f:
                json.dump(self.ltm, f, indent=2)
        except Exception as e:
            print(f"[Memory Error] Failed to save LTM for {self.agent_name}: {e}")

    def add_to_stm(self, role: str, content: str):
        """Adds a conversation message to the Short-Term sliding window memory."""
        self.stm.append({"role": role, "content": content})
        if len(self.stm) > self.max_stm_turns * 2: # 2 entries per turn (user + assistant)
            self.stm = self.stm[-self.max_stm_turns * 2:]

    def clear_stm(self):
        """Clears current sliding conversation history."""
        self.stm = []

    def add_to_ltm(self, query: str, resolution: str, code_snippets: Optional[List[str]] = None):
        """Saves a successfully completed run/skill to the episodic LTM database and ChromaDB."""
        record = {
            "query": query,
            "resolution": resolution,
            "code_snippets": code_snippets or [],
            "timestamp": datetime.now().isoformat()
        }
        self.ltm.append(record)
        self._save_ltm()

        # Ingest to ChromaDB
        if self.collection:
            try:
                import time
                doc_id = f"episode_{len(self.ltm)}_{int(time.time())}"
                doc_text = f"Query: {query}\nResolution: {resolution}"
                if code_snippets:
                    doc_text += f"\nCode: {chr(10).join(code_snippets)}"
                
                self.collection.add(
                    documents=[doc_text],
                    metadatas=[{
                        "type": "episode", 
                        "query": query, 
                        "resolution": resolution,
                        "code_snippets": json.dumps(code_snippets or []),
                        "timestamp": record["timestamp"]
                    }],
                    ids=[doc_id]
                )
            except Exception as e:
                print(f"[Memory Warning] Failed to index episode into ChromaDB: {e}")

    def add_semantic_fact(self, fact: str, fact_type: str = "preference"):
        """Saves a semantic fact or user preference to the ChromaDB database."""
        if self.collection:
            try:
                import time
                doc_id = f"fact_{int(time.time())}"
                self.collection.add(
                    documents=[fact],
                    metadatas=[{
                        "type": fact_type,
                        "timestamp": datetime.now().isoformat()
                    }],
                    ids=[doc_id]
                )
                print(f"[Memory] Fact ingested: '{fact}' ({fact_type})")
            except Exception as e:
                print(f"[Memory Warning] Failed to index fact into ChromaDB: {e}")

    def search_ltm(self, query: str, limit: int = 2) -> List[dict]:
        """
        Retrieves top similar past successful episodes or facts from LTM.
        Uses ChromaDB if active, otherwise falls back to token-based similarity.
        """
        if not self.collection:
            return self._search_ltm_fallback(query, limit)

        try:
            # Query ChromaDB collection
            res = self.collection.query(
                query_texts=[query],
                n_results=limit
            )
            
            results = []
            if res and "ids" in res and res["ids"]:
                matching_ids = res["ids"][0]
                metas = res["metadatas"][0] if "metadatas" in res and res["metadatas"] else []
                docs = res.get("documents", [[]])[0] if res.get("documents") else []
                
                for i in range(len(matching_ids)):
                    doc_id = matching_ids[i]
                    meta = metas[i] if i < len(metas) else {}
                    doc_text = docs[i] if i < len(docs) else ""
                    
                    # Check if it's an episode or fact
                    if meta.get("type") == "episode":
                        # Match original record from self.ltm list
                        orig_query = meta.get("query")
                        match_record = None
                        for record in self.ltm:
                            if record.get("query") == orig_query:
                                match_record = record
                                break
                        if match_record:
                            results.append(match_record)
                        else:
                            # Reconstruct from metadata
                            try:
                                code_list = json.loads(meta.get("code_snippets", "[]"))
                            except Exception:
                                code_list = []
                            results.append({
                                "query": orig_query,
                                "resolution": meta.get("resolution", ""),
                                "code_snippets": code_list,
                                "timestamp": meta.get("timestamp", "")
                            })
                    else:
                        # It's a semantic fact, structure it to match expected query format
                        results.append({
                            "query": f"Semantic Fact: {meta.get('type', 'preference')}",
                            "resolution": doc_text,
                            "code_snippets": [],
                            "timestamp": meta.get("timestamp", "")
                        })

            # If nothing returned, fallback to token similarity search
            if not results:
                return self._search_ltm_fallback(query, limit)
                
            return results
        except Exception as e:
            print(f"[Memory Warning] ChromaDB search failed: {e}. Falling back to token search...")
            return self._search_ltm_fallback(query, limit)

    def _search_ltm_fallback(self, query: str, limit: int = 2) -> List[dict]:
        """Fallback token-based similarity search logic."""
        if not self.ltm:
            return []

        # Use Overlap Coefficient
        def calculate_similarity(s1: str, s2: str) -> float:
            tokens1 = set(re.findall(r"\w+", s1.lower()))
            tokens2 = set(re.findall(r"\w+", s2.lower()))
            if not tokens1 or not tokens2:
                return 0.0
            intersection = tokens1.intersection(tokens2)
            return len(intersection) / min(len(tokens1), len(tokens2))

        scored_records = []
        for record in self.ltm:
            score = calculate_similarity(query, record["query"])
            scored_records.append((score, record))

        scored_records.sort(key=lambda x: x[0], reverse=True)
        results = [rec for score, rec in scored_records if score >= 0.2]
        return results[:limit]

    def get_stm_as_list(self) -> List[Dict[str, str]]:
        """Returns dialog history formatted for LLM client input."""
        return self.stm

    def _load_workflow_state(self) -> dict:
        """Loads persistent workflow state from disk."""
        default_state = {
            "last_query": None,
            "last_action": None,
            "last_error": None,
            "active_topic": None
        }
        if not os.path.exists(self.state_path):
            return default_state
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
                for k, v in default_state.items():
                    if k not in state:
                        state[k] = v
                return state
        except Exception as e:
            print(f"[Memory Error] Failed to load workflow state for {self.agent_name}: {e}")
            return default_state

    def _save_workflow_state(self):
        """Saves active workflow state to disk."""
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(self.workflow_state, f, indent=2)
        except Exception as e:
            print(f"[Memory Error] Failed to save workflow state for {self.agent_name}: {e}")

    def update_workflow_state(self, last_query: str = None, last_action: str = None, last_error: str = None, active_topic: str = None):
        """Updates the episodic workflow/sequence tracking state."""
        if last_query is not None:
            self.workflow_state["last_query"] = last_query
        if last_action is not None:
            self.workflow_state["last_action"] = last_action
        if last_error is not None:
            self.workflow_state["last_error"] = last_error
        if active_topic is not None:
            self.workflow_state["active_topic"] = active_topic
        self._save_workflow_state()

    def get_workflow_state(self) -> dict:
        """Retrieves the active workflow context."""
        return self.workflow_state
