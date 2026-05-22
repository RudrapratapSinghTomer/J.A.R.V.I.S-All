import os
import re
from openai import OpenAI
from core.sandbox import DockerSandbox

class CLIEngine:
    """
    Self-Validating CLI Engine.
    Executes terminal commands and Python scripts within the Docker sandbox,
    analyzes output tracebacks and exit codes, and automatically uses an LLM
    self-correction loop to fix and retry failures.
    """
    def __init__(self, sandbox: DockerSandbox, llm_client: OpenAI = None, model: str = "meta/llama-3.3-70b-instruct"):
        self.sandbox = sandbox
        self.llm_client = llm_client
        self.model = model
        self.max_retries = 7

    def execute_and_validate(self, command: str, workdir: str = "/workspace") -> dict:
        """
        Executes a command inside the sandbox.
        If it fails, attempts self-correction up to max_retries.
        """
        print(f"[CLI] Running: '{command}'")
        res = self.sandbox.execute_command(command, workdir=workdir)
        
        if res["success"]:
            print("[CLI] Success!")
            return res

        # If it failed, check if we have LLM capabilities to self-correct
        if not self.llm_client:
            print(f"[CLI] Command failed (Exit code: {res['exit_code']}). No LLM client configured for self-correction.")
            return res

        retry_count = 0
        current_cmd = command
        last_error = res["stderr"] or res["stdout"]

        while retry_count < self.max_retries:
            retry_count += 1
            print(f"\n[CLI] Attempting self-correction {retry_count}/{self.max_retries} due to failure...")
            print(f"[CLI] Error to correct:\n--- START ERROR ---\n{last_error}\n--- END ERROR ---")

            correction = self._request_self_correction(current_cmd, last_error)
            if not correction or "fixed_command" not in correction:
                print("[CLI] LLM failed to generate a correction strategy.")
                break

            explanation = correction.get("explanation", "No explanation.")
            pre_commands = correction.get("pre_commands", [])
            fixed_command = correction["fixed_command"]

            print(f"[CLI] Strategy: {explanation}")
            
            # Execute any pre-requisite commands (like pip install or directory creation)
            pre_success = True
            for pre_cmd in pre_commands:
                print(f"[CLI] Running pre-requisite: '{pre_cmd}'")
                pre_res = self.sandbox.execute_command(pre_cmd, workdir=workdir)
                if not pre_res["success"]:
                    print(f"[CLI] Pre-requisite command failed: '{pre_cmd}'. Error: {pre_res['stderr']}")
                    last_error = pre_res["stderr"] or pre_res["stdout"]
                    pre_success = False
                    break
            
            if not pre_success:
                continue

            # Execute fixed command
            print(f"[CLI] Running corrected command: '{fixed_command}'")
            res = self.sandbox.execute_command(fixed_command, workdir=workdir)
            if res["success"]:
                print("[CLI] Self-correction succeeded!")
                return res
            
            last_error = res["stderr"] or res["stdout"]
            current_cmd = fixed_command

        print(f"[CLI] Max retries reached. Command failed.")
        return res

    def _request_self_correction(self, command: str, error_msg: str) -> dict:
        """Calls the LLM to get a structured JSON fix for the error."""
        prompt = (
            "You are the J.A.R.V.I.S 10.0 Terminal Self-Correction Agent.\n"
            "An executive terminal command failed inside our sandbox environment.\n"
            "Analyze the command, exit status, and traceback, then formulate a correction strategy.\n\n"
            f"FAILED COMMAND: {command}\n\n"
            f"TRACEBACK / ERROR:\n{error_msg}\n\n"
            "### CRITICAL ERROR-PATTERN GUIDELINES:\n"
            "1. Sandbox Dependency Isolation: If Docker sandbox is active, ALL library installations (e.g. `pip install <package>`) "
            "MUST happen inside the sandbox container workspace. Never leak packages or run commands outside the designated sandbox context.\n"
            "2. Sequential Setup vs Execution: Do NOT attempt to run scripts or execute commands that import/rely on libraries "
            "BEFORE their installations have successfully completed. If an import fails, specify the correct installation command "
            "as a 'pre_command' so it completes BEFORE the corrected command is retried.\n"
            "3. Shell Syntax & Encodings: Ensure shell quoting and file paths match the environment rules (Windows host vs bash guest).\n\n"
            "Provide your response in JSON format. You can optionally include list of 'pre_commands' "
            "(e.g., install missing packages, create folders) and MUST provide the revised 'fixed_command' "
            "that resolves the original goal.\n\n"
            "### Response Schema:\n"
            "{\n"
            "  \"explanation\": \"Brief explanation of what went wrong (e.g. missing import, wrong syntax)\",\n"
            "  \"pre_commands\": [\"list of shell commands to run first before retrying, if any\"],\n"
            "  \"fixed_command\": \"the final corrected terminal command to run\"\n"
            "}\n"
            "Ensure the response is valid JSON and nothing else."
        )

        try:
            completion = self.llm_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            import json
            response_text = completion.choices[0].message.content
            return json.loads(response_text)
        except Exception as e:
            # Retry without response_format in case the API doesn't support it
            if "response_format" in str(e).lower() or "unsupported" in str(e).lower():
                try:
                    import json
                    completion = self.llm_client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.1
                    )
                    response_text = completion.choices[0].message.content
                    return json.loads(response_text)
                except Exception as retry_e:
                    print(f"[CLI Error] LLM Correction retry also failed: {retry_e}")
                    return {}
            print(f"[CLI Error] LLM Correction call failed: {e}")
            return {}
