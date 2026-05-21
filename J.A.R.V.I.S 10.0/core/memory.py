import os
import json
import re
import yaml
from typing import List, Dict, Optional

# Load config
_CONFIG_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "config.yaml"))
with open(_CONFIG_PATH, "r") as f:
    _CFG = yaml.safe_load(f)

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

        if env_caps:
            context_parts.extend([
                "\n--- SYSTEM CAPABILITIES ---",
                f"- OS Environment: {env_caps.get('guest_os', env_caps.get('host_os', 'Unknown'))}",
                f"- Python Version: {env_caps.get('python_version', 'Unknown')}",
                f"- GPU Support: {'CUDA GPU Available' if env_caps.get('gpu_available') else 'CPU Only'}",
                f"- Pip Available: {env_caps.get('pip_available')}",
                f"- Git Available: {env_caps.get('git_available')}",
                f"- NPM Available: {env_caps.get('npm_available')}",
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
    Long-Term Memory (LTM / LSTM) saving history to local json files.
    """
    def __init__(self, agent_name: str, max_stm_turns: int = 10):
        self.agent_name = agent_name
        self.max_stm_turns = max_stm_turns
        self.stm: List[Dict[str, str]] = []
        
        # Determine LTM path inside J.A.R.V.I.S 10.0/memory/
        self.memory_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "memory"))
        os.makedirs(self.memory_dir, exist_ok=True)
        self.ltm_path = os.path.join(self.memory_dir, f"ltm_{self.agent_name.lower()}.json")
        
        self.ltm = self._load_ltm()

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
        """Saves a successfully completed run/skill to the episodic LTM database."""
        record = {
            "query": query,
            "resolution": resolution,
            "code_snippets": code_snippets or [],
            "timestamp": os.getenv("CURRENT_TIME", "")
        }
        self.ltm.append(record)
        self._save_ltm()

    def search_ltm(self, query: str, limit: int = 2) -> List[dict]:
        """
        Retrieves top similar past successful episodes from LTM using token-based similarity.
        Provides local vector-like retrieval without requiring a heavy external DB.
        """
        if not self.ltm:
            return []

        # Use Overlap Coefficient: size of intersection divided by size of smaller set
        # This is extremely resilient for partial/keyword queries in longer sentences
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

        # Sort by score descending
        scored_records.sort(key=lambda x: x[0], reverse=True)
        
        # Filter records with a minimal similarity threshold
        results = [rec for score, rec in scored_records if score >= 0.2]
        return results[:limit]

    def get_stm_as_list(self) -> List[Dict[str, str]]:
        """Returns dialog history formatted for LLM client input."""
        return self.stm
