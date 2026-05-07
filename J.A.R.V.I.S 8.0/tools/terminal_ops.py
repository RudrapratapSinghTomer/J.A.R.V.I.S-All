import subprocess
import os
import sys

def run_command(command: str, cwd: str = None, timeout: int = 30) -> dict:
    """
    Executes a shell command and returns the results.
    
    Args:
        command: The shell command to run.
        cwd: The working directory (defaults to current).
        timeout: Execution timeout in seconds.
        
    Returns:
        dict: {'success': bool, 'stdout': str, 'stderr': str, 'returncode': int}
    """
    if not cwd:
        cwd = os.getcwd()
        
    try:
        # Use shell=True for complex commands/pipes, but be mindful of security
        # In a controlled agentic environment, this is often necessary.
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
            "returncode": -1
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "returncode": -1
        }

def list_directory(path: str = ".") -> str:
    """Returns a formatted list of files and directories."""
    try:
        items = os.listdir(path)
        return "\n".join(items)
    except Exception as e:
        return f"Error listing directory: {e}"

def get_system_info() -> str:
    """Returns basic system environment information."""
    import platform
    return f"OS: {platform.system()} {platform.release()}\nPython: {sys.version}\nCWD: {os.getcwd()}"
