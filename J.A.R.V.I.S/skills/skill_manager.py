import os
import importlib
import logging
import sys
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger("jarvis.skills.manager")

class SkillManager:
    """
    Manages the AI Lifecycle of J.A.R.V.I.S's skills.
    Allows for autonomous skill creation, hot-reloading, and execution.
    """
    def __init__(self):
        self.skills_dir = Path(__file__).parent
        self.loaded_skills: Dict[str, Any] = {}

    def load_skill(self, skill_name: str) -> Any:
        """Dynamically load or reload a skill module."""
        try:
            module_name = f"skills.{skill_name}"
            if module_name in sys.modules:
                importlib.reload(sys.modules[module_name])
                logger.info(f"Skill reloaded: {skill_name}")
            else:
                importlib.import_module(module_name)
                logger.info(f"Skill loaded: {skill_name}")
            
            self.loaded_skills[skill_name] = sys.modules[module_name]
            return self.loaded_skills[skill_name]
        except Exception as e:
            logger.error(f"Failed to load skill {skill_name}: {e}")
            return None

    def create_and_load_skill(self, skill_name: str, code: str) -> bool:
        """Autonomously write a new skill file and load it into the system."""
        try:
            skill_file = self.skills_dir / f"{skill_name}.py"
            with open(skill_file, "w", encoding="utf-8") as f:
                f.write(code)
            
            logger.info(f"New skill written: {skill_name}.py")
            return self.load_skill(skill_name) is not None
        except Exception as e:
            logger.error(f"Failed to create skill {skill_name}: {e}")
            return False

    def execute_skill_method(self, skill_name: str, method_name: str, *args, **kwargs) -> Any:
        """Execute a method on a dynamically loaded skill."""
        skill_module = self.loaded_skills.get(skill_name) or self.load_skill(skill_name)
        if skill_module:
            method = getattr(skill_module, method_name, None)
            if method:
                if callable(method):
                    return method(*args, **kwargs)
                return method
            logger.warning(f"Method {method_name} not found in skill {skill_name}")
        return None

# Global instance
skill_manager = SkillManager()
