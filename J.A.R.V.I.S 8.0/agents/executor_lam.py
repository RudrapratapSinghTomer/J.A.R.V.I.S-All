import os
import subprocess
import tempfile
import sys
import yaml
import re

config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
with open(config_path, "r") as f:
    config = yaml.safe_load(f)

# The repo root that Jarvis is allowed to operate in
REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


class ExecutorLAM:
    """
    Large Action Model (LAM) executor — P.A.L. (Program-Aided Language) pattern.

    Workflow:
    1. Receives a natural-language action query from the orchestrator.
    2. For git/file tasks: delegates directly to tools/git_ops.py (reliable, auditable).
    3. For general tasks: uses NVIDIA NIM to generate a Python action script.
    4. Runs the script inside a Docker sandbox (256 MB limit, 30s timeout).
       Falls back to a guarded subprocess if Docker is unavailable.
    5. On failure, uses PAL self-correction: sends the error back to NIM
       to get a fixed script, then retries once.
    6. Returns the output string back to the orchestrator.
    """

    # --- Keywords that signal a git/file action ---
    GIT_KEYWORDS = [
        "readme",
        "commit",
        "push",
        "git",
        "create file",
        "write file",
        "add file",
        "repository",
        "repo",
    ]

    def __init__(self):
        self.nvidia_key = os.getenv("NVIDIA_API_KEY")
        self.nvidia_model = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct")

    # ------------------------------------------------------------------
    # Public interface called by the orchestrator
    # ------------------------------------------------------------------
    def execute_action(self, query: str) -> str:
        """
        Entry point. Decides whether to use the git tool or
        generate + run a Python script.
        """
        query_lower = query.lower()

        if any(kw in query_lower for kw in self.GIT_KEYWORDS):
            return self._handle_git_action(query)

        # General case: ask LLM to write a script, then run it
        script = self._generate_script(query)
        if script:
            return self._run_script(script)
        return "[Executor] Could not generate an action script for this query."

    # ------------------------------------------------------------------
    # Git / file actions
    # ------------------------------------------------------------------
    def _handle_git_action(self, query: str) -> str:
        """
        For git tasks, ask the LLM what content to write and which file,
        then use git_ops to do the real commit + push.
        """
        from tools.git_ops import write_and_commit

        repo_root = self._detect_repo_root()

        # Ask the LLM to produce structured output we can parse
        prompt = (
            f"You are JARVIS executing a git file-creation task.\n"
            f"Task: {query}\n\n"
            f"Repository root: {repo_root}\n\n"
            "Respond ONLY in this exact format (no extra text):\n"
            "FILE: <relative path from repo root>\n"
            "COMMIT: <git commit message>\n"
            "CONTENT:\n"
            "<full file content here>\n"
        )

        structured = self._call_cloud_llm(prompt, max_tokens=2048)
        if not structured:
            return "[Executor] Cloud LLM did not respond for git action generation."

        # Parse the LLM response
        file_path, commit_msg, content = self._parse_git_response(structured)
        if not file_path or not content:
            return f"[Executor] Could not parse LLM git response.\nRaw LLM output:\n{structured}"

        print(f"[Executor] Writing '{file_path}' and committing to git...")
        result = write_and_commit(
            repo_path=repo_root,
            file_relative_path=file_path,
            content=content,
            commit_message=commit_msg,
            push=True,
        )
        return result

    def _parse_git_response(self, text: str):
        """Parse FILE:, COMMIT:, CONTENT: from LLM structured output."""
        file_path = None
        commit_msg = "Jarvis: automated commit"
        content = None

        file_match = re.search(r"^FILE:\s*(.+)$", text, re.MULTILINE)
        commit_match = re.search(r"^COMMIT:\s*(.+)$", text, re.MULTILINE)
        content_match = re.search(r"^CONTENT:\n([\s\S]+)", text)

        if file_match:
            file_path = file_match.group(1).strip()
        if commit_match:
            commit_msg = commit_match.group(1).strip()
        if content_match:
            content = content_match.group(1).strip()

        return file_path, commit_msg, content

    # ------------------------------------------------------------------
    # General script generation + execution
    # ------------------------------------------------------------------
    def _generate_script(self, query: str) -> str | None:
        """Ask the cloud LLM to write a Python script for the given task."""
        prompt = (
            f"You are JARVIS. Write a Python 3 script to accomplish this task:\n\n"
            f"{query}\n\n"
            "Requirements:\n"
            "- Output ONLY the raw Python code, no markdown fences.\n"
            "- The script must be self-contained and safe to run.\n"
            "- Print a clear success/failure message at the end.\n"
        )
        return self._call_cloud_llm(prompt, max_tokens=1024)

    def _run_script(self, script_code: str) -> str:
        """
        Run a Python script inside a Docker sandbox (P.A.L. pattern).
        Falls back to a plain subprocess if Docker is not available.
        The script is given a 30-second timeout in both modes.
        """
        # --- Try Docker first (sandboxed, isolated) ---
        try:
            import docker  # type: ignore
            client = docker.from_env(timeout=10)
            image = config.get("docker", {}).get("sandbox_image", "python:3.10-slim")

            print(f"[Executor] Running script in Docker sandbox ({image})...")
            result = client.containers.run(
                image=image,
                command=["python", "-c", script_code],
                remove=True,          # Auto-delete container after run
                mem_limit="256m",     # Memory cap
                network_disabled=False,
                stdout=True,
                stderr=True,
                timeout=30,
            )
            output = result.decode("utf-8") if isinstance(result, bytes) else str(result)
            return f"[Docker Success]\n{output}"

        except ImportError:
            print("[Executor] Docker SDK not installed. Falling back to subprocess.")
        except Exception as docker_err:
            print(f"[Executor] Docker unavailable ({docker_err}). Falling back to subprocess.")

        # --- Subprocess fallback ---
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as tmp:
                tmp.write(script_code)
                tmp_path = tmp.name

            result = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                text=True,
                timeout=30,
            )
            os.unlink(tmp_path)

            if result.returncode == 0:
                return f"[Success]\n{result.stdout}"
            else:
                # PAL self-correction: pass error back to LLM and retry once
                error_info = f"Exit {result.returncode}\n{result.stderr}\n{result.stdout}"
                print(f"[Executor] Script failed, attempting self-correction...\n{error_info}")
                corrected = self._correct_script(script_code, error_info)
                if corrected:
                    with tempfile.NamedTemporaryFile(
                        mode="w", suffix=".py", delete=False, encoding="utf-8"
                    ) as tmp2:
                        tmp2.write(corrected)
                        tmp2_path = tmp2.name
                    result2 = subprocess.run(
                        [sys.executable, tmp2_path],
                        capture_output=True, text=True, timeout=30,
                    )
                    os.unlink(tmp2_path)
                    if result2.returncode == 0:
                        return f"[Corrected & Success]\n{result2.stdout}"
                    return f"[Error after correction - Exit {result2.returncode}]\n{result2.stderr}"
                return f"[Error - Exit {result.returncode}]\n{result.stderr}\n{result.stdout}"
        except Exception as e:
            return f"[System Error] {e}"

    def _correct_script(self, original_script: str, error: str) -> str | None:
        """Ask the LLM to fix a script given its error output (PAL self-correction)."""
        prompt = (
            "A Python script failed with the following error. Fix it and return ONLY the corrected Python code, "
            "no markdown fences.\n\n"
            f"ORIGINAL SCRIPT:\n{original_script}\n\n"
            f"ERROR:\n{error}\n"
        )
        return self._call_cloud_llm(prompt, max_tokens=1024)


    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _call_cloud_llm(self, prompt: str, max_tokens: int = 1024) -> str | None:
        """Call NVIDIA NIM and return the text response."""
        try:
            from openai import OpenAI

            client = OpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=self.nvidia_key,
            )
            completion = client.chat.completions.create(
                model=self.nvidia_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=max_tokens,
            )
            return completion.choices[0].message.content
        except Exception as e:
            print(f"[Executor] Cloud LLM call failed: {e}")
            return None

    def _detect_repo_root(self) -> str:
        """
        Returns the path to the top-level git repo root by walking up
        from the current file location.
        """
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        while path != os.path.dirname(path):
            if os.path.isdir(os.path.join(path, ".git")):
                return path
            path = os.path.dirname(path)
        # Fallback — the J.A.R.V.I.S All directory
        return os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

    # Keep backward-compat alias
    def generate_and_execute(self, query: str) -> str:
        return self.execute_action(query)
