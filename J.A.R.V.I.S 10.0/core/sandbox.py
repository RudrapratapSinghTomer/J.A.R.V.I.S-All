import os
import sys
import docker
import subprocess
from core.config_loader import load_config

# Load config
_CFG = load_config()


DOCKER_CFG = _CFG.get("docker", {})
IMAGE_NAME = DOCKER_CFG.get("sandbox_image", "jarvis-sandbox:latest")
CONTAINER_NAME = DOCKER_CFG.get("container_name", "jarvis_sandbox_env")

# The workspace path on the host
REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))


class DockerSandbox:
    def __init__(self):
        self.is_fallback_mode = False
        try:
            self.client = docker.from_env(timeout=5)
            # Ping to confirm Docker daemon is responsive
            self.client.ping()
        except Exception as e:
            error_str = str(e)
            if "CreateFile" in error_str or "FileNotFoundError" in error_str:
                print("[Sandbox Info] Docker not detected locally. Activating safe subprocess execution fallback.")
            else:
                print(f"[Sandbox Warning] Docker offline or unavailable: {error_str}")
                print("[Sandbox Info] Activating safe local subprocess execution fallback.")
            self.client = None
            self.is_fallback_mode = True
            
        self.container = None
        self._cached_caps = None

    def ensure_container_running(self) -> bool:
        """Checks if the persistent container is running. Fallback mode always returns True."""
        if self.is_fallback_mode:
            return True

        if not self.client:
            self.is_fallback_mode = True
            return True

        try:
            # Check if container already exists
            self.container = self.client.containers.get(CONTAINER_NAME)
            if self.container.status != "running":
                print(f"[Sandbox] Starting existing container: {CONTAINER_NAME}...")
                self.container.start()
            return True
        except docker.errors.NotFound:
            print(f"[Sandbox] Container '{CONTAINER_NAME}' not found. Initializing...")
            return self._build_and_start_container()
        except Exception as e:
            print(f"[Sandbox Error] Failed to get/start container: {e}. Switching to Subprocess Fallback.")
            self.is_fallback_mode = True
            return True

    def _build_and_start_container(self) -> bool:
        """Builds the Docker image if needed and starts the persistent container."""
        if not self.client:
            return False

        dockerfile_dir = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
        try:
            self.client.images.get(IMAGE_NAME)
            print(f"[Sandbox] Image '{IMAGE_NAME}' already built.")
        except docker.errors.ImageNotFound:
            print(f"[Sandbox] Image '{IMAGE_NAME}' not found. Building from Dockerfile in {dockerfile_dir}...")
            try:
                self.client.images.build(
                    path=dockerfile_dir,
                    tag=IMAGE_NAME,
                    rm=True
                )
                print(f"[Sandbox] Successfully built image '{IMAGE_NAME}'.")
            except Exception as build_err:
                print(f"[Sandbox Error] Failed to build image: {build_err}")
                return False

        try:
            volumes = {
                REPO_ROOT: {
                    "bind": "/workspace",
                    "mode": "rw"
                }
            }
            print(f"[Sandbox] Launching container '{CONTAINER_NAME}' mounting '{REPO_ROOT}'...")
            self.container = self.client.containers.run(
                image=IMAGE_NAME,
                name=CONTAINER_NAME,
                detach=True,
                volumes=volumes,
                mem_limit="1g",
                network_mode="host",
                restart_policy={"Name": "unless-stopped"}
            )
            print(f"[Sandbox] Container '{CONTAINER_NAME}' successfully launched.")
            return True
        except Exception as run_err:
            print(f"[Sandbox Error] Failed to launch container: {run_err}")
            return False

    def execute_command(self, cmd: str, workdir: str = "/workspace") -> dict:
        """Runs a command inside the container (or host shell if in fallback mode)."""
        if not self.ensure_container_running():
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "Sandbox system initialization failure."
            }

        if self.is_fallback_mode:
            return self._execute_subprocess_fallback(cmd, workdir)

        try:
            exec_cmd = ["/bin/bash", "-c", cmd]
            result = self.container.exec_run(
                cmd=exec_cmd,
                workdir=workdir,
                demux=True
            )
            
            exit_code = result.exit_code
            stdout_bytes, stderr_bytes = result.output or (b"", b"")
            
            stdout = stdout_bytes.decode("utf-8", errors="ignore") if stdout_bytes else ""
            stderr = stderr_bytes.decode("utf-8", errors="ignore") if stderr_bytes else ""
            
            return {
                "success": exit_code == 0,
                "exit_code": exit_code,
                "stdout": stdout.strip(),
                "stderr": stderr.strip()
            }
        except Exception as e:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Docker Exec execution error: {e}"
            }

    def _execute_subprocess_fallback(self, cmd: str, workdir: str) -> dict:
        """Fallback: executes commands on the host machine using subprocess."""
        # Convert /workspace inside docker to the actual repo root path on the host
        if workdir.startswith("/workspace"):
            sub_path = workdir[len("/workspace"):].lstrip("/").lstrip("\\")
            host_cwd = os.path.normpath(os.path.join(REPO_ROOT, sub_path))
        else:
            host_cwd = REPO_ROOT

        # Standardize path in host
        if not os.path.exists(host_cwd):
            host_cwd = REPO_ROOT

        try:
            # Run command on host system (Windows)
            # Use shell=True for complete environmental execution
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=host_cwd,
                capture_output=True,
                text=True,
                timeout=60
            )
            return {
                "success": result.returncode == 0,
                "exit_code": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip()
            }
        except Exception as e:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Subprocess execution error: {e}"
            }

    def stop_container(self):
        """Stops the running container if any."""
        if self.container:
            try:
                self.container.stop()
                print(f"[Sandbox] Container '{CONTAINER_NAME}' stopped.")
            except Exception as e:
                print(f"[Sandbox Error] Failed to stop container: {e}")

    def probe_capabilities(self) -> dict:
        """
        Probes the executing environment's capabilities and limitations.
        Runs once and caches the result.
        """
        if self._cached_caps:
            return self._cached_caps

        caps = {
            "sandbox_mode": "Docker Persistent Container" if not self.is_fallback_mode else "Safe Local Subprocess Fallback",
            "host_os": os.name,
            "python_version": sys.version.split()[0],
            "gpu_available": False,
            "git_available": False,
            "npm_available": False,
            "pip_available": False,
            "limitations": []
        }

        # Probe via execute_command to get exact runtime environment parameters
        py_exe = sys.executable if self.is_fallback_mode else "python"
        py_probe = (
            "import sys, platform, shutil; "
            "print(sys.version.split()[0]); "
            "print(platform.system() + ' ' + platform.release()); "
            "print(shutil.which('git') is not None); "
            "print(shutil.which('npm') is not None); "
            "print(shutil.which('pip') is not None)"
        )
        res = self.execute_command(f'{py_exe} -c "{py_probe}"')
        if res["success"] and res["stdout"]:
            lines = [l.strip() for l in res["stdout"].split("\n") if l.strip()]
            if len(lines) >= 5:
                caps["python_version"] = lines[0]
                caps["guest_os"] = lines[1]
                caps["git_available"] = lines[2].lower() == "true"
                caps["npm_available"] = lines[3].lower() == "true"
                caps["pip_available"] = lines[4].lower() == "true"
        
        # Probe for CUDA / GPU support
        gpu_probe_script = (
            "import sys\n"
            "c = False\n"
            "try:\n"
            "    import torch\n"
            "    c = torch.cuda.is_available()\n"
            "except:\n"
            "    pass\n"
            "print(c)"
        )
        gpu_res = self.execute_command(f"{py_exe} -c \"{gpu_probe_script}\"")
        if gpu_res["success"] and "true" in gpu_res["stdout"].lower():
            caps["gpu_available"] = True
        else:
            # Try nvidia-smi as fallback
            smi_res = self.execute_command("nvidia-smi")
            if smi_res["success"]:
                caps["gpu_available"] = True

        # Synthesize clear and actionable limitations
        if not caps["gpu_available"]:
            caps["limitations"].append("No CUDA GPU available. Deep learning models must run on CPU (will be slower).")
        if not caps["git_available"]:
            caps["limitations"].append("Git command-line tool is not installed or not in PATH.")
        if not caps["npm_available"]:
            caps["limitations"].append("Node/NPM is not installed. Node.js backend or frontend tasks are restricted.")
        if self.is_fallback_mode:
            caps["limitations"].append("Operating in safe host subprocess fallback mode (Docker Desktop is offline). Environmental leaks are possible, clean after use.")
        else:
            caps["limitations"].append("Running inside Docker container. Any changes to files outside /workspace will not persist after container restarts.")

        self._cached_caps = caps
        return caps


