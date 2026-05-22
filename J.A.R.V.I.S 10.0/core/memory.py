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
            "timestamp": datetime.now().isoformat()
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
