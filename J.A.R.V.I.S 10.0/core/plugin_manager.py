import os
import json
import importlib.util

class PluginManager:
    """
    Manages dynamic loading and execution of Antigravity capabilities (plugins).
    """
    def __init__(self, workspace_root: str):
        self.workspace_root = workspace_root
        self.registry_path = os.path.join(workspace_root, "capabilities", "registry.json")
        self.registry = self._load_registry()
        self.loaded_plugins = {}

    def _load_registry(self) -> dict:
        if not os.path.exists(self.registry_path):
            return {"capabilities": {}}
        try:
            with open(self.registry_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[PluginManager] Error loading registry: {e}")
            return {"capabilities": {}}

    def reload_registry(self):
        """Reloads the registry file from disk."""
        self.registry = self._load_registry()

    def _load_plugin_module(self, capability_name: str, entrypoint: str):
        if capability_name in self.loaded_plugins:
            return self.loaded_plugins[capability_name]
        
        full_path = os.path.join(self.workspace_root, os.path.normpath(entrypoint))
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"Plugin entrypoint not found: {full_path}")
            
        module_name = f"capabilities.plugins.{capability_name}"
        spec = importlib.util.spec_from_file_location(module_name, full_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, "PluginInstance"):
                instance = module.PluginInstance()
                if hasattr(instance, "load"):
                    instance.load()
                self.loaded_plugins[capability_name] = instance
                return instance
            else:
                raise AttributeError(f"Plugin {capability_name} missing 'PluginInstance' class.")
        raise ImportError(f"Failed to load module for {capability_name}")

    def execute_plugin(self, capability_name: str, inputs: dict) -> dict:
        """Executes a loaded plugin with the provided inputs."""
        capability = self.registry.get("capabilities", {}).get(capability_name)
        if not capability:
            return {"success": False, "error": f"Capability '{capability_name}' not found in registry."}
            
        entrypoint = capability.get("entrypoint")
        if not entrypoint:
            return {"success": False, "error": f"Capability '{capability_name}' missing entrypoint."}
            
        try:
            plugin = self._load_plugin_module(capability_name, entrypoint)
            if hasattr(plugin, "execute"):
                return plugin.execute(inputs)
            else:
                return {"success": False, "error": f"Plugin '{capability_name}' missing 'execute' method."}
        except Exception as e:
            return {"success": False, "error": f"Error executing plugin '{capability_name}': {str(e)}"}
