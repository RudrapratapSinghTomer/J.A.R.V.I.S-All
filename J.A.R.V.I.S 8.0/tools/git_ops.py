import subprocess
import os


def run_git(args: list, cwd: str) -> dict:
    """
    Runs a git command in the given directory.
    Returns {'success': bool, 'stdout': str, 'stderr': str}.
    """
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e)}


def write_and_commit(
    repo_path: str,
    file_relative_path: str,
    content: str,
    commit_message: str,
    push: bool = True,
) -> str:
    """
    Writes a file inside a git repo, stages it, commits it, and optionally pushes.

    Args:
        repo_path:           Absolute path to the git repository root.
        file_relative_path:  Path of the file relative to the repo root.
        content:             The text content to write.
        commit_message:      Git commit message.
        push:                Whether to push to origin after committing.

    Returns:
        A summary string of what happened.
    """
    abs_file_path = os.path.join(repo_path, file_relative_path)

    # --- Write the file ---
    try:
        parent_dir = os.path.dirname(abs_file_path)
        if parent_dir:  # Guard: dirname is empty when writing to repo root
            os.makedirs(parent_dir, exist_ok=True)
        with open(abs_file_path, "w", encoding="utf-8") as f:
            f.write(content)
        write_result = f"[Git] Wrote file: {abs_file_path}"
    except Exception as e:
        return f"[Git] Error writing file: {e}"

    # --- git add ---
    add = run_git(["add", file_relative_path], cwd=repo_path)
    if not add["success"]:
        return f"[Git] 'git add' failed: {add['stderr']}"

    # --- git commit ---
    commit = run_git(["commit", "-m", commit_message], cwd=repo_path)
    if not commit["success"]:
        # Check if there is simply nothing to commit (already up-to-date)
        if "nothing to commit" in commit["stdout"] + commit["stderr"]:
            return "[Git] Nothing to commit — file already exists with same content."
        return f"[Git] 'git commit' failed: {commit['stderr']}\n{commit['stdout']}"

    # --- git push ---
    if push:
        push_result = run_git(["push"], cwd=repo_path)
        if not push_result["success"]:
            return (
                f"[Git] Committed locally but 'git push' failed: {push_result['stderr']}\n"
                f"Commit output: {commit['stdout']}"
            )
        return (
            f"{write_result}\n"
            f"[Git] Committed: {commit['stdout']}\n"
            f"[Git] Pushed:    {push_result['stdout']}"
        )

    return f"{write_result}\n[Git] Committed: {commit['stdout']}"


def git_status(repo_path: str) -> str:
    """Returns the current git status of a repository."""
    result = run_git(["status", "--short"], cwd=repo_path)
    return result["stdout"] if result["success"] else f"[Git] Error: {result['stderr']}"


def git_log(repo_path: str, n: int = 5) -> str:
    """Returns last n commits."""
    result = run_git(["log", "--oneline", f"-{n}"], cwd=repo_path)
    return result["stdout"] if result["success"] else f"[Git] Error: {result['stderr']}"
