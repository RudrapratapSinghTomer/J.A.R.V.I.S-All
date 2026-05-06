import os
import psutil
import logging
import asyncio
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
from memory.cognee_bridge import memory
from skills.workspace_scanner import workspace_scanner

logger = logging.getLogger("jarvis.skills.system_explorer")

class SystemExplorer:
    """
    Skill for gaining 'Full System Knowledge'.
    Provides J.A.R.V.I.S with access to the Windows filesystem, running processes, and system logs.
    """
    def __init__(self):
        self.workspace_root = Path(__file__).parent.parent
        self.max_search_depth = 5

    async def search_filesystem(self, query: str, root: str = "C:\\", extension: Optional[str] = None) -> List[str]:
        """
        Search for files across the Windows filesystem.
        Optimized with depth limiting and keyword matching.
        """
        logger.info(f"Searching filesystem for: {query} in {root}")
        results = []
        try:
            # We use a fast recursive search for specific directories or a throttled scan
            # To prevent hanging J.A.R.V.I.S, we limit the search
            loop = asyncio.get_running_loop()
            
            def _scan():
                found = []
                # Prioritize common locations first if root is C:\
                scan_paths = [root]
                if root == "C:\\":
                    scan_paths = [
                        os.path.expanduser("~/Desktop"),
                        os.path.expanduser("~/Documents"),
                        os.path.expanduser("~/Downloads"),
                        "C:\\Projects" # Common dev path
                    ]
                
                for start_path in scan_paths:
                    if not os.path.exists(start_path): continue
                    for dirpath, dirnames, filenames in os.walk(start_path):
                        # Limit depth
                        depth = dirpath.count(os.sep) - start_path.count(os.sep)
                        if depth > self.max_search_depth:
                            del dirnames[:] # Don't go deeper
                            continue
                            
                        for f in filenames:
                            if query.lower() in f.lower():
                                if extension and not f.endswith(extension):
                                    continue
                                found.append(os.path.join(dirpath, f))
                                if len(found) >= 20: return found
                return found

            results = await loop.run_in_executor(None, _scan)
            return results
        except Exception as e:
            logger.error(f"Filesystem search failed: {e}")
            return []

    async def list_active_processes(self, filter_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """List currently running processes with resource usage metrics."""
        processes = []
        try:
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    pinfo = proc.info
                    if filter_name and filter_name.lower() not in pinfo['name'].lower():
                        continue
                    processes.append(pinfo)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            
            # Sort by CPU usage
            processes.sort(key=lambda x: x['cpu_percent'], reverse=True)
            return processes[:20] # Return top 20
        except Exception as e:
            logger.error(f"Process list failed: {e}")
            return []

    async def read_system_logs(self, count: int = 50) -> str:
        """Read the latest Windows System Event logs using PowerShell."""
        logger.info(f"Retrieving latest {count} system event logs...")
        try:
            cmd = f"Get-EventLog -LogName System -Newest {count} | Select-Object TimeGenerated, EntryType, Source, Message | Format-List"
            proc = await asyncio.create_subprocess_exec(
                "powershell", "-Command", cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            if stderr:
                logger.error(f"PowerShell error: {stderr.decode()}")
                return "Failed to retrieve system logs."
            return stdout.decode()
        except Exception as e:
            logger.error(f"Log retrieval failed: {e}")
            return str(e)

    async def get_system_summary(self) -> str:
        """Generate a high-level summary of system state."""
        procs = await self.list_active_processes()
        top_proc = procs[0]['name'] if procs else "None"
        
        # Check disk usage
        disk = psutil.disk_usage('C:\\')
        
        summary = (
            f"System Status: {psutil.cpu_percent()}% CPU usage. "
            f"Top process: {top_proc}. "
            f"Disk C: {disk.percent}% full ({disk.free // (2**30)}GB free)."
        )
        return summary

    async def sync_workspace_to_memory(self):
        """
        Deep Neural Sync: Crawls all projects in the workspace and ingests 
        key metadata and logic into Cognee memory.
        """
        logger.info("Initiating Full Neural Sync of workspace...")
        scan_report = await workspace_scanner.scan()
        projects = workspace_scanner.known_projects
        
        ingested_count = 0
        for name, data in projects.items():
            project_path = Path(data["path"])
            
            # 1. Ingest Project Metadata
            meta_text = f"Project: {name}\nPath: {data['path']}\nType: {data['type']}\nGit Status: {data['git_status']}"
            await memory.remember(meta_text, metadata={"type": "project_meta", "name": name})
            
            # 2. Ingest Key Files (README, package.json, etc.)
            key_files = ["README.md", "package.json", "requirements.txt", "pyproject.toml"]
            for kf in key_files:
                fpath = project_path / kf
                if fpath.exists():
                    try:
                        content = fpath.read_text(encoding="utf-8", errors="ignore")
                        await memory.remember(f"File: {kf} in {name}\nContent:\n{content[:2000]}", 
                                            metadata={"type": "project_file", "project": name, "file": kf})
                        ingested_count += 1
                    except: pass
            
        # 3. Finalize Memory Graph
        if ingested_count > 0:
            logger.info(f"Buffered {ingested_count} project files. Consolidating knowledge graph...")
            await memory.improve()
            return f"Successfully synchronized {len(projects)} projects and {ingested_count} key files into memory."
        
        return "Workspace scan completed, but no significant files were found for ingestion."

# Global instance
system_explorer = SystemExplorer()
