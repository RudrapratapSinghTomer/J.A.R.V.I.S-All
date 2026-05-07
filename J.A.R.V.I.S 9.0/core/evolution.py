import os
import time
import threading
from scanner import scan_workspace
from analyzer import Analyzer
from memory import Memory
from planner import Planner


class EvolutionCore:
    def __init__(self, stop_event: threading.Event):
        self.stop_event = stop_event
        self.analyzer = Analyzer()
        self.memory = Memory()
        self.planner = Planner()
        self.is_paused = False

        # Root workspace is parent of J.A.R.V.I.S 9.0
        self.root_workspace = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )

    def get_jarvis_versions(self):
        versions = {}
        for item in os.listdir(self.root_workspace):
            full_path = os.path.join(self.root_workspace, item)
            if os.path.isdir(full_path) and ("J.A.R.V.I.S" in item or "Jarvis" in item):
                # Don't analyze self (9.0) to avoid recursion
                if "9.0" not in item:
                    versions[item] = full_path
        return versions

    def run_cycle(self):
        """The main autonomous loop."""
        print("[Evolution] Background Consciousness initialized.")

        while not self.stop_event.is_set():
            if self.is_paused:
                time.sleep(1)
                continue

            versions = self.get_jarvis_versions()

            for v_name, v_path in versions.items():
                if self.stop_event.is_set() or self.is_paused:
                    break

                # Check if already fully analyzed in memory
                if self.memory.is_version_analyzed(v_name):
                    continue

                print(f"\n[Evolution] Analyzing legacy version: {v_name}...")

                # Scan
                codebase = scan_workspace(v_path)
                if not codebase:
                    continue

                # Analyze (NIM Cloud)
                if self.stop_event.is_set() or self.is_paused:
                    break
                features = self.analyzer.analyze_codebase(
                    v_name, codebase, stop_event=self.stop_event
                )

                # Store
                if self.stop_event.is_set() or self.is_paused:
                    break
                added = self.memory.add_features(features)

                # Plan
                if self.stop_event.is_set() or self.is_paused:
                    break
                jarvis_9_state = "A foundational architecture with a scanner, analyzer, memory, and planner modules, preparing for feature assimilation."
                for feature in features:
                    if self.stop_event.is_set() or self.is_paused:
                        break
                    self.planner.generate_plan(
                        feature, jarvis_9_state, stop_event=self.stop_event
                    )

                print(
                    f"[Evolution] Mastered {v_name}. Discovered {len(features)} features."
                )

            # Sleep a bit before next check to keep CPU usage low
            time.sleep(10)

    def pause(self):
        if not self.is_paused:
            print("[Evolution] User command received. Pausing background analysis...")
            self.is_paused = True

    def resume(self):
        if self.is_paused:
            print("[Evolution] System idle. Resuming background analysis...")
            self.is_paused = False
