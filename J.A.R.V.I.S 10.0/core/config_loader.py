import os
import yaml

_DIR = os.path.dirname(os.path.abspath(__file__))
_BASE_CONFIG_PATH = os.path.normpath(os.path.join(_DIR, "..", "config.yaml"))
_LOCAL_CONFIG_PATH = os.path.normpath(os.path.join(_DIR, "..", "config.local.yaml"))
_REPO_ROOT = os.path.normpath(os.path.join(_DIR, "..", ".."))

def _deep_merge(dict1: dict, dict2: dict) -> dict:
    """Recursively merges dict2 into dict1."""
    for key, value in dict2.items():
        if key in dict1 and isinstance(dict1[key], dict) and isinstance(value, dict):
            _deep_merge(dict1[key], value)
        else:
            dict1[key] = value
    return dict1

_cached_cfg = None

def load_config() -> dict:
    """Loads configuration by merging base config.yaml and optional config.local.yaml. Caches result."""
    global _cached_cfg
    if _cached_cfg is not None:
        return _cached_cfg

    config = {}
    
    # 1. Load base configuration
    if os.path.exists(_BASE_CONFIG_PATH):
        try:
            with open(_BASE_CONFIG_PATH, "r") as f:
                base_cfg = yaml.safe_load(f)
                if isinstance(base_cfg, dict):
                    config = base_cfg
        except Exception as e:
            print(f"[Config Loader Warning] Failed to parse config.yaml: {e}")
            
    # 2. Merge local overrides if they exist
    if os.path.exists(_LOCAL_CONFIG_PATH):
        try:
            with open(_LOCAL_CONFIG_PATH, "r") as f:
                local_cfg = yaml.safe_load(f)
                if isinstance(local_cfg, dict):
                    config = _deep_merge(config, local_cfg)
                    print(f"[Config Loader] Merged override configurations from config.local.yaml")
        except Exception as e:
            print(f"[Config Loader Warning] Failed to parse config.local.yaml: {e}")

    # 3. Dynamic absolute allowed write directory resolution to keep portable
    sec_cfg = config.setdefault("security", {})
    allowed_dir = sec_cfg.get("allowed_write_directory")
    
    # Fallback if hardcoded or not existing
    if not allowed_dir or allowed_dir == "C:/Users/developer/Desktop/J.A.R.V.I.S All" or not os.path.isabs(allowed_dir):
        sec_cfg["allowed_write_directory"] = _REPO_ROOT

    # Ensure path separators are standardized
    sec_cfg["allowed_write_directory"] = os.path.normpath(sec_cfg["allowed_write_directory"])
    
    _cached_cfg = config
    return config
