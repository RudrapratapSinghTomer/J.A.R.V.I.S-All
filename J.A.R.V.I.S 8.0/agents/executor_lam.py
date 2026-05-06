import docker
import os
import yaml
import tempfile
import sys

config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
with open(config_path, "r") as f:
    config = yaml.safe_load(f)

SANDBOX_IMAGE = config.get("docker", {}).get("sandbox_image", "python:3.10-slim")


class ExecutorLAM:
    def __init__(self):
        try:
            self.client = docker.from_env()
            # Try to ping to ensure docker daemon is running
            self.client.ping()
        except Exception as e:
            print(f"[Executor] Failed to connect to Docker daemon: {e}")
            self.client = None

    def execute_action(self, script_code: str) -> str:
        """
        Executes a Python script securely inside a Docker container.
        This represents the Large Action Model's P.A.L. execution.
        """
        if not self.client:
            return (
                "[Executor] Docker is not available. Cannot execute LAM actions safely."
            )

        try:
            # We first need to write the script to a temporary file locally so we can mount it
            # Or we can just pass it via a command if it's short, but a file is more robust.
            # Actually, the python alpine image allows passing a script via stdin or -c
            # Let's use the container's run command to execute it directly to avoid mount issues.

            escaped_code = script_code.replace('"', '\\"')

            print("[Executor] Starting sandboxed execution...")
            container = self.client.containers.run(
                SANDBOX_IMAGE,
                command=["python", "-c", script_code],
                detach=True,
                mem_limit="100m",  # Limit memory
                network_disabled=True,  # Prevent it from calling out unless we want it to
                remove=False,  # Keep it so we can grab logs
            )

            result = container.wait(timeout=10)  # 10 second timeout
            logs = container.logs().decode("utf-8")

            container.remove(force=True)

            if result["StatusCode"] == 0:
                return f"[Success]\n{logs}"
            else:
                return f"[Error - Exit Code {result['StatusCode']}]\n{logs}"

        except docker.errors.ContainerError as e:
            return f"[Execution Error]\n{e}"
        except Exception as e:
            return f"[System Error]\n{e}"

    def generate_and_execute(self, query: str) -> str:
        """
        Placeholder for generating code via LLM and then executing it.
        Currently just returns a mock for testing the orchestration.
        """
        # In a full implementation, we'd call an LLM (local or cloud) to write the script
        mock_script = "print('Executed action for: " + query.replace("'", "\\'") + "')"
        return self.execute_action(mock_script)
