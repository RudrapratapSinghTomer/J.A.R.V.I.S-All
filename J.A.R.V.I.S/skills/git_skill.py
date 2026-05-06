import os
import asyncio
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("jarvis.skills.git")

class GitSkill:
    """
    Skill for autonomous Git operations.
    Enables J.A.R.V.I.S to pull, branch, fix, commit, and push changes.
    """
    def __init__(self, workspace_root: Optional[str] = None):
        self.workspace_root = Path(workspace_root) if workspace_root else Path(__file__).parent.parent.parent

    async def _run_git_cmd(self, args: List[str], cwd: Path) -> str:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", *args,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                err = stderr.decode().strip()
                logger.error(f"Git command failed: git {' '.join(args)} - {err}")
                return f"ERROR: {err}"
            return stdout.decode().strip()
        except Exception as e:
            logger.error(f"Git execution error: {e}")
            return f"EXCEPTION: {str(e)}"

    async def sync_repo(self, path: str) -> str:
        """Pull latest changes."""
        logger.info(f"Syncing repo at {path}...")
        return await self._run_git_cmd(["pull", "origin", "main"], Path(path))

    async def create_branch(self, path: str, branch_name: str) -> str:
        """Create and switch to a new branch."""
        logger.info(f"Creating branch {branch_name} in {path}...")
        return await self._run_git_cmd(["checkout", "-b", branch_name], Path(path))

    async def commit_and_push(self, path: str, message: str, branch: str = "main") -> str:
        """Add all changes, commit, and push."""
        cwd = Path(path)
        logger.info(f"Committing changes in {path}: {message}")
        
        await self._run_git_cmd(["add", "."], cwd)
        commit_res = await self._run_git_cmd(["commit", "-m", message], cwd)
        if "ERROR" in commit_res:
            return commit_res
            
        return await self._run_git_cmd(["push", "origin", branch], cwd)

    async def autonomous_fix_and_push(self, path: str, issue_description: str):
        """
        High-level autonomous flow: Branch -> Fix (via Engineer) -> Commit -> Push.
        """
        cwd = Path(path)
        branch_name = f"fix/jarvis-auto-{int(asyncio.get_event_loop().time())}"
        
        # 1. Create Branch
        await self.create_branch(path, branch_name)
        
        # 2. Fix (This would normally call engineer_skill, but we'll simulate the intention here)
        logger.info(f"J.A.R.V.I.S is autonomously fixing: {issue_description}")
        # In a real scenario, we'd trigger engineer_skill.execute(issue_description)
        
        # 3. Commit & Push
        return await self.commit_and_push(path, f"🤖 J.A.R.V.I.S. Autonomous Fix: {issue_description}", branch_name)

# Global instance
git_skill = GitSkill()
