import os
import yaml
from pathlib import Path

# Load config to get allowed directory
config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
with open(config_path, "r") as f:
    config = yaml.safe_load(f)

ALLOWED_WRITE_DIR = Path(
    config.get("security", {}).get("allowed_write_directory", "")
).resolve()


def is_path_safe_for_write(filepath: str) -> bool:
    """
    Checks if a given file path is within the allowed write directory.
    This prevents Jarvis 8.0 from editing other versions like J.A.R.V.I.S 9.0.
    """
    try:
        # Resolve the target path to get an absolute, normalized path
        target_path = Path(filepath).resolve()

        # Check if the target path is a subpath of the allowed directory
        # We also check if ALLOWED_WRITE_DIR exists to ensure config is correct
        if not ALLOWED_WRITE_DIR.exists():
            return False

        return target_path.is_relative_to(ALLOWED_WRITE_DIR)
    except Exception as e:
        print(f"[Security] Error validating path {filepath}: {e}")
        return False


def check_write_permission(filepath: str):
    """
    Raises a PermissionError if the path is not allowed.
    """
    if not is_path_safe_for_write(filepath):
        raise PermissionError(
            f"Security Violation: Attempted to write to {filepath}, "
            f"which is outside the allowed directory {ALLOWED_WRITE_DIR}."
        )
