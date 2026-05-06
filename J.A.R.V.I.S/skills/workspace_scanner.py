import os
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger("jarvis.skills.workspace_scanner")

class WorkspaceScanner:
    """
    Autonomously maps active projects, detects build failures, and 
    identifies logical next steps for J.A.R.V.I.S. to take.
    """
    def __init__(self, roots: List[str] = None):
        if roots is None:
            # Default to Desktop and common project locations
            self.roots = [
                Path(os.path.expanduser("~/Desktop")),
                Path(__file__).parent.parent.parent # The JARVIS directory itself
            ]
        else:
            self.roots = [Path(r) for r in roots]
            
        self.known_projects: Dict[str, Dict[str, Any]] = {}

    async def scan(self) -> Dict[str, Any]:
        """Perform a full scan of all configured root directories."""
        logger.info("Starting autonomous workspace scan...")
        report = {
            "projects_found": 0,
            "anomalies": [],
            "suggestions": []
        }
        
        for root in self.roots:
            if not root.exists():
                continue
                
            for item in root.iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    # Check if it's a project (e.g., has .git, package.json, requirements.txt)
                    if self._is_project(item):
                        report["projects_found"] += 1
                        project_data = await self._analyze_project(item)
                        self.known_projects[item.name] = project_data
                        
                        if project_data.get("has_errors"):
                            report["anomalies"].append({
                                "project": item.name,
                                "issue": "Detected potential build or runtime errors in logs/files."
                            })
                            report["suggestions"].append(f"Investigate and fix issues in '{item.name}'.")
        
        return report

    def _is_project(self, path: Path) -> bool:
        indicators = [".git", "package.json", "requirements.txt", "pyproject.toml", "pom.xml", "go.mod"]
        return any((path / ind).exists() for ind in indicators)

    async def _analyze_project(self, path: Path) -> Dict[str, Any]:
        """Deep dive into a project to check health and status."""
        data = {
            "path": str(path),
            "type": self._detect_language(path),
            "has_errors": False,
            "git_status": "unknown"
        }
        
        # Check Git Status
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "status", "--short",
                cwd=str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            data["git_status"] = "dirty" if stdout.decode().strip() else "clean"
        except:
            pass
            
        # Check for error indicators in logs or output
        # (This is a simplified check for now)
        if (path / "logs").exists():
            for log_file in (path / "logs").glob("*.log"):
                if self._file_contains(log_file, ["ERROR", "CRITICAL", "Exception", "Traceback"]):
                    data["has_errors"] = True
                    break
        
        return data

    def _detect_language(self, path: Path) -> str:
        if (path / "package.json").exists(): return "javascript/typescript"
        if (path / "requirements.txt").exists() or (path / "pyproject.toml").exists(): return "python"
        if (path / "pom.xml").exists(): return "java/maven"
        if (path / "go.mod").exists(): return "go"
        return "unknown"

    def _file_contains(self, path: Path, keywords: List[str]) -> bool:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                # Read last 100 lines for efficiency
                import collections
                last_lines = collections.deque(f, 100)
                content = "".join(last_lines)
                return any(kw in content for kw in keywords)
        except:
            return False

# Global instance
workspace_scanner = WorkspaceScanner()
