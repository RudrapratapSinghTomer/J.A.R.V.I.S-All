import os
import hashlib
import subprocess


def scan_workspace(root_path: str):
    """
    Scans the workspace using git ls-files for speed, or os.walk as a fallback.
    """
    scanned_data = []

    # Try git ls-files first
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=root_path,
            capture_output=True,
            text=True,
            check=True,
        )
        files = result.stdout.splitlines()
        for rel_path in files:
            # Skip common junk extensions
            if rel_path.endswith(
                (".pyc", ".pyo", ".db", ".log", ".png", ".jpg", ".jpeg", ".gif")
            ):
                continue

            file_path = os.path.join(root_path, rel_path)
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(1000)
                scanned_data.append(
                    {
                        "path": rel_path,
                        "type": "file",
                        "name": os.path.basename(rel_path),
                        "preview": content,
                    }
                )
            except:
                continue
        return scanned_data
    except Exception:
        # Fallback to os.walk
        for root, dirs, files in os.walk(root_path):
            dirs[:] = [
                d
                for d in dirs
                if not d.startswith(".")
                and d
                not in (
                    "__pycache__",
                    "node_modules",
                    "venv",
                    ".venv",
                    "data",
                    "chroma_db",
                    "site-packages",
                )
            ]
            rel_root = os.path.relpath(root, root_path)
            if rel_root != ".":
                scanned_data.append(
                    {
                        "path": rel_root,
                        "type": "directory",
                        "name": os.path.basename(root),
                    }
                )
            for file in files:
                if file.startswith(".") or file.endswith(
                    (".pyc", ".pyo", ".db", ".log")
                ):
                    continue
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, root_path)
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read(1000)
                    scanned_data.append(
                        {
                            "path": rel_path,
                            "type": "file",
                            "name": file,
                            "preview": content,
                        }
                    )
                except:
                    continue
        return scanned_data


def get_file_hash(file_path: str):
    """Computes MD5 hash of a file."""
    hasher = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return None
