import os

EXCLUDED_DIRS = {
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    "scratch",
    "dist",
    "build",
    ".claude",
    ".claude-flow",
    ".claw",
    ".jarvis",
}
EXCLUDED_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".db",
    ".sqlite",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".mp4",
    ".mp3",
    ".wav",
    ".lock",
}
ALLOWED_EXTENSIONS = {
    ".py",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".txt",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".html",
    ".css",
    ".sh",
}


def scan_workspace(root_path: str) -> dict:
    """
    Scans the directory and returns a dictionary of relative_path -> content
    """
    codebase = {}

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Modifying dirnames in-place to skip excluded directories
        dirnames[:] = [
            d for d in dirnames if d not in EXCLUDED_DIRS and not d.startswith(".")
        ]

        # Skip J.A.R.V.I.S 9.0 plans directory from scanning
        if "J.A.R.V.I.S 9.0\\plans" in dirpath or "J.A.R.V.I.S 9.0/plans" in dirpath:
            continue

        for file in filenames:
            ext = os.path.splitext(file)[1].lower()
            if ext in ALLOWED_EXTENSIONS and ext not in EXCLUDED_EXTENSIONS:
                full_path = os.path.join(dirpath, file)
                rel_path = os.path.relpath(full_path, root_path)
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        codebase[rel_path] = f.read()
                except Exception:
                    pass
    return codebase
