import os
import time
import threading
import logging
from typing import Optional
from core.scanner import scan_workspace
from core.memory_mhc import MHC_Memory
from core.planner import Planner
from agents.researcher import AutoResearcher


class BackgroundConsciousness:
    def __init__(self, stop_event: threading.Event, memory: MHC_Memory):
        self.stop_event = stop_event
        self.memory = memory
        self.planner = Planner(memory)
        self.researcher = AutoResearcher()
        self.is_paused = False
        self.is_scanning = False

        # Root workspace is parent of J.A.R.V.I.S 8.0
        self.root_workspace = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )

        # Setup logging
        log_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "consciousness.log"
        )
        logging.basicConfig(
            filename=log_path,
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
        )

    def start(self):
        """Main entry point for the background thread."""
        logging.info("Background Consciousness initialized.")
        print("[Consciousness] Background loop active.")

        # Step 1: Initial Full-System Scan
        self._initial_ingestion()

        # Step 2: Continuous Idle Loop
        self.run_cycle()

    def _initial_ingestion(self):
        """Performs a one-time full scan of the J.A.R.V.I.S All directory."""
        print(f"[Consciousness] Ingestion check: root={self.root_workspace}")
        if self.memory.has_learned("INITIAL_SYSTEM_SCAN_COMPLETE"):
            logging.info("Initial system scan already complete. Skipping.")
            print("[Consciousness] Initial scan already complete.")
            return

        print("[Consciousness] Performing initial full-system awareness scan...")
        self.is_scanning = True

        try:
            items = scan_workspace(self.root_workspace)
            total = len(items)
            print(f"[Consciousness] Found {total} items to ingest.")

            for i, item in enumerate(items):
                if self.stop_event.is_set():
                    break

                if (i + 1) % 10 == 0:
                    print(
                        f"[Consciousness] Progress: {i + 1}/{total} items ingested..."
                    )

                # Create a concise fact from the scanned item
                fact = f"System Entity: {item['type']} at {item['path']}. "
                if item["type"] == "file":
                    fact += f"Content preview: {item.get('preview', '')[:200]}"

                # Add to memory manifold
                self.memory.add_to_manifold(
                    "system",
                    fact,
                    metadata={"path": item["path"], "type": item["type"]},
                )
                logging.info(f"Ingested {item['path']}")

            self.memory.add_to_manifold(
                "system",
                "INITIAL_SYSTEM_SCAN_COMPLETE",
                metadata={"type": "checkpoint"},
            )
            print("[Consciousness] Initial awareness scan complete.")
        except Exception as e:
            logging.error(f"Initial ingestion failed: {e}")
        finally:
            self.is_scanning = False

    def run_cycle(self):
        """The main autonomous 'Idle' loop."""
        while not self.stop_event.is_set():
            if self.is_paused:
                time.sleep(1)
                continue

            # 1. Incremental Awareness: Check for changes in current project
            self._incremental_scan()

            # 2. Visual Reflection: Analyze environment (Screen + Webcam)
            if not self.is_paused and not self.stop_event.is_set():
                self._visual_reflection()

            # 3. Deep Thought: Autonomous Research & Planning
            if not self.is_paused and not self.stop_event.is_set():
                self._autonomous_planning()
                self._run_research_lab()

            # Sleep to keep CPU usage low
            time.sleep(30)

    def _visual_reflection(self):
        """Uses the threaded vision system to save environmental context to memory."""
        logging.info("Starting visual reflection...")
        try:
            from agents.vision_vlm import VisionVLM

            vision = VisionVLM()
            summary = vision.capture_dual_vision(
                "Briefly describe the current screen and user environment."
            )
            self.memory.add_to_manifold("system", f"Visual Memory: {summary}")
            vision.stop()
        except Exception as e:
            logging.error(f"Visual reflection failed: {e}")

    def _run_research_lab(self):
        """Triggers the Karpathy-style autonomous research loop."""
        logging.info("Triggering autonomous research lab...")
        lab_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "research_lab")
        )

        try:
            import subprocess

            # Run the preparation and then the 'training' (experiment)
            subprocess.run(["python", "prepare.py"], cwd=lab_path, capture_output=True)
            subprocess.run(["python", "train.py"], cwd=lab_path, capture_output=True)
            logging.info("Research lab cycle complete.")
        except Exception as e:
            logging.error(f"Research lab failed: {e}")

    def _incremental_scan(self):
        """Scans only for new or modified features."""
        # Focus on current version (8.0) and root files
        current_path = os.path.join(self.root_workspace, "J.A.R.V.I.S 8.0")
        logging.info("Performing incremental scan...")

        items = scan_workspace(current_path)
        for item in items:
            if self.stop_event.is_set() or self.is_paused:
                break

            content_summary = item.get("preview", item.get("name", ""))
            if not self.memory.has_learned(content_summary):
                logging.info(f"Learning new feature: {item['path']}")
                self.memory.add_to_manifold(
                    "system",
                    f"Updated Feature: {item['path']} - {content_summary[:500]}",
                )

    def _autonomous_planning(self):
        """Triggers the Planner for selective high-value tasks."""
        logging.info("Starting autonomous planning phase...")

        # Get recent context to decide what to plan
        context = self.memory.get_context(
            "system", "current system health and development priorities"
        )

        # Trigger the selective architect
        # This will be implemented in planner.py
        self.planner.generate_autonomous_plans(context)

    def pause(self):
        if not self.is_paused:
            logging.info("Pausing background consciousness...")
            self.is_paused = True

    def resume(self):
        if self.is_paused:
            logging.info("Resuming background consciousness...")
            self.is_paused = False

    def stop(self):
        self.stop_event.set()
        logging.info("Background consciousness stopped.")
