import os
import json
import yaml
import subprocess
from typing import Dict, List, Optional

class AntigravitySkillLoader:
    """
    Loads and integrates Antigravity awesome-skills library into J.A.R.V.I.S 10.0
    """
    def __init__(self, cli_engine=None):
        self.cli_engine = cli_engine
        self.skills_cache = {}
        self.repo_url = "https://github.com/sickn33/antigravity-awesome-skills.git"
        self.skills_dir = None

    def fetch_skills_library(self, target_dir: str = None) -> bool:
        """Download or update the Antigravity awesome-skills library"""
        if target_dir is None:
            target_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "external_skills", "antigravity"))
        
        os.makedirs(target_dir, exist_ok=True)
        
        # Clone or update the repository
        if os.path.exists(os.path.join(target_dir, ".git")):
            print("[AntigravityLoader] Updating existing skills repository...")
            try:
                import git
                repo = git.Repo(target_dir)
                origin = repo.remotes.origin
                origin.pull()
                print("[AntigravityLoader] Successfully pulled updates via GitPython.")
                self.skills_dir = target_dir
                return True
            except Exception as e:
                print(f"[AntigravityLoader Warning] GitPython pull failed: {e}. Trying subprocess fallback...")
                result = subprocess.run(
                    ["git", "-C", target_dir, "pull"],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    self.skills_dir = target_dir
                    return True
                else:
                    print(f"[AntigravityLoader] Subprocess Git pull failed: {result.stderr}")
                    return False
        else:
            print("[AntigravityLoader] Cloning Antigravity skills library...")
            try:
                import git
                git.Repo.clone_from(self.repo_url, target_dir)
                print("[AntigravityLoader] Successfully cloned repository via GitPython.")
                self.skills_dir = target_dir
                return True
            except Exception as e:
                print(f"[AntigravityLoader Warning] GitPython clone failed: {e}. Trying subprocess fallback...")
                result = subprocess.run(
                    ["git", "clone", self.repo_url, target_dir],
                    capture_output=True,
                    text=True
                )
                if result.returncode == 0:
                    self.skills_dir = target_dir
                    return True
                else:
                    print(f"[AntigravityLoader] Subprocess Git clone failed: {result.stderr}")
                    return False

    def discover_available_skills(self) -> Dict[str, Dict]:
        """Scan and index all available skills from the library"""
        if not self.skills_dir:
            # Try to fetch if not yet loaded
            if not self.fetch_skills_library():
                return {}
        
        skills = {}
        
        # 1. Parse the pre-compiled skills_index.json if available
        index_path = os.path.join(self.skills_dir, "data", "skills_index.json")
        if os.path.exists(index_path):
            try:
                with open(index_path, 'r', encoding='utf-8') as f:
                    index_data = json.load(f)
                if isinstance(index_data, list):
                    for skill_entry in index_data:
                        if isinstance(skill_entry, dict):
                            skill_name = skill_entry.get('name') or skill_entry.get('id')
                            if skill_name:
                                rel_path = skill_entry.get('path', f"skills/{skill_name}")
                                full_path = os.path.normpath(os.path.join(self.skills_dir, rel_path))
                                skills[skill_name] = {
                                    'path': full_path,
                                    'metadata': skill_entry,
                                    'type': 'index_json'
                                }
            except Exception as e:
                if os.getenv("JARVIS_DEBUG") == "true":
                    print(f"[AntigravityLoader] Failed to parse skills index {index_path}: {e}")
        
        # 2. Walk the directory as a fallback scan for custom json/yaml configs
        for root, dirs, files in os.walk(self.skills_dir):
            # Skip hidden metadata folders
            if ".git" in root or "__pycache__" in root:
                continue
                
            for file in files:
                if file.endswith(('.json', '.yaml', '.yml')):
                    # Avoid parsing catalog/index files that are not individual skills
                    if file in ('package.json', 'package-lock.json', 'skills_index.json', 'catalog.json', 'workflows.json'):
                        continue
                    skill_path = os.path.normpath(os.path.join(root, file))
                    try:
                        with open(skill_path, 'r', encoding='utf-8') as f:
                            if file.endswith('.json'):
                                skill_data = json.load(f)
                            else:
                                skill_data = yaml.safe_load(f)
                        
                        if isinstance(skill_data, dict):
                            skill_name = skill_data.get('name', file.replace('.json', '').replace('.yaml', '').replace('.yml', ''))
                            if skill_name not in skills:
                                skills[skill_name] = {
                                    'path': skill_path,
                                    'metadata': skill_data,
                                    'type': 'json' if file.endswith('.json') else 'yaml'
                                }
                    except Exception as e:
                        if os.getenv("JARVIS_DEBUG") == "true":
                            print(f"[AntigravityLoader] Failed to parse {skill_path}: {e}")
        
        self.skills_cache = skills
        return skills

    def get_skill_by_name(self, skill_name: str) -> Optional[Dict]:
        """Retrieve a specific skill by name"""
        if not self.skills_cache:
            self.discover_available_skills()
        return self.skills_cache.get(skill_name)

    def filter_skills_by_query(self, query: str) -> List[Dict]:
        """Filter skills based on user query using keyword and tag matching"""
        if not self.skills_cache:
            self.discover_available_skills()
            
        matching_skills = []
        query_lower = query.lower()
        
        for skill_name, skill_data in self.skills_cache.items():
            metadata = skill_data.get('metadata', {})
            description = metadata.get('description', '').lower()
            tags = [tag.lower() for tag in metadata.get('tags', [])]
            
            if (query_lower in skill_name.lower() or 
                query_lower in description or 
                any(query_lower in tag for tag in tags)):
                matching_skills.append({
                    'name': skill_name,
                    **skill_data
                })
        
        return matching_skills
