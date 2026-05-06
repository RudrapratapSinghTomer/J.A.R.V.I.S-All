import os
from dotenv import load_dotenv
from core.scanner import scan_workspace
from core.analyzer import Analyzer
from core.memory import Memory
from core.planner import Planner


def get_jarvis_versions(root_path: str):
    """Finds all J.A.R.V.I.S version folders in the given root path."""
    versions = {}
    for item in os.listdir(root_path):
        full_path = os.path.join(root_path, item)
        if os.path.isdir(full_path) and ("J.A.R.V.I.S" in item or "Jarvis" in item):
            versions[item] = full_path
    return versions


def main():
    # Load environment variables (NVIDIA_API_KEY)
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

    # We assume the parent directory is J.A.R.V.I.S All
    root_workspace = os.path.dirname(os.path.dirname(__file__))

    print(f"Starting J.A.R.V.I.S 9.0 Evolution Loop in {root_workspace}")

    versions = get_jarvis_versions(root_workspace)
    print(f"Detected {len(versions)} J.A.R.V.I.S instances.")

    analyzer = Analyzer()
    memory = Memory()
    planner = Planner()

    # Phase 1: Scan and Analyze all versions
    for v_name, v_path in versions.items():
        print(f"\\n--- Scanning {v_name} ---")
        codebase = scan_workspace(v_path)
        print(f"Scanned {len(codebase)} files in {v_name}.")

        if len(codebase) == 0:
            continue

        features = analyzer.analyze_codebase(v_name, codebase)
        added = memory.add_features(features)
        print(
            f"Discovered {len(features)} features. Added {added} new features to Memory."
        )

    # Phase 2: Plan integration for discovered features
    print("\\n--- Commencing Feature Planning ---")
    jarvis_9_state = "A foundational architecture with a scanner, analyzer, memory, and planner modules, preparing for feature assimilation."

    all_features = memory.get_all_features()
    for feature in all_features:
        planner.generate_plan(feature, jarvis_9_state)

    print(
        "\\nEvolution Cycle Complete. Check the 'plans/' directory for new feature blueprints."
    )


if __name__ == "__main__":
    main()
