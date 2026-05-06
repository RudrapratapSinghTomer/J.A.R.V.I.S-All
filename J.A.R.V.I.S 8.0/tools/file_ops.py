import os
import sys

# Add jarvis-os root to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from core.security import check_write_permission


def read_file(filepath: str) -> str:
    """
    Reads a file. Jarvis 8.0 can read from anywhere.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file {filepath}: {e}"


def write_file(filepath: str, content: str) -> str:
    """
    Writes to a file. Jarvis 8.0 can ONLY write to its allowed directory.
    """
    try:
        # This will raise an exception if not allowed
        check_write_permission(filepath)

        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote to {filepath}"
    except PermissionError as pe:
        return str(pe)
    except Exception as e:
        return f"Error writing file {filepath}: {e}"


def list_directory(dirpath: str) -> list:
    """
    Lists contents of a directory. Unrestricted reading.
    """
    try:
        return os.listdir(dirpath)
    except Exception as e:
        return [f"Error listing directory {dirpath}: {e}"]
