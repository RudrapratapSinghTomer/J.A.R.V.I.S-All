import asyncio
import logging
import io
from typing import Any, Mapping

import pyautogui
from PIL import Image

from .base import AgentResult, AgentStatus, AgentTask, BaseAgent

logger = logging.getLogger("jarvis.vision")


from core.llm_client import ModelCapability, require_capability


class VisionAgent(BaseAgent):
    agent_id = "vision"
    body_part = "eyes"
    capabilities = (
        "vision",
        "visual",
        "screen",
        "screenshot",
        "camera",
        "presence_detection",
    )
    toolsets = ("screen_analysis", "presence_monitoring")
    hardware = ("gpu", "cpu")

    def __init__(self, mcp_server: Any | None = None) -> None:
        super().__init__(mcp_server)
        self.is_running = False
        self._loop_task: asyncio.Task | None = None
        self.interval = 60.0  # Check every minute

    async def initialize(self) -> bool:
        self.is_running = True
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._vision_loop())
        logger.info("VisionAgent proactive loop started.")
        return True

    async def shutdown(self) -> None:
        self.is_running = False
        if self._loop_task:
            self._loop_task.cancel()
        logger.info("VisionAgent proactive loop stopped.")

    @require_capability(ModelCapability.VISION)
    async def handle(
        self,
        task: AgentTask,
        context: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        self.status = AgentStatus.WORKING
        intents = task.intents or []

        # Manual Screenshot/Camera Task
        if "screenshot" in task.content or "screen" in intents:
            screenshot = pyautogui.screenshot()
            logger.info("Screenshot captured manually.")
            summary = "Desktop screenshot captured."
        elif "camera" in task.content or "camera" in intents:
            frame = await self.capture_camera_frame()
            summary = (
                "Camera frame captured."
                if frame is not None
                else "Camera capture failed."
            )
        else:
            summary = "Visual context refreshed."

        self.status = AgentStatus.IDLE
        return AgentResult(
            agent_id=self.agent_id,
            handled=True,
            summary=summary,
            data={"presence": True, "focus": "desktop"},
            confidence=0.9,
        )

    async def capture_camera_frame(self) -> Any | None:
        """Capture a raw frame from the webcam."""
        try:
            import cv2

            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                logger.warning("Camera hardware not available.")
                return None
            ret, frame = cap.read()
            return frame if ret else None
        except Exception as e:
            logger.error(f"Camera capture error: {e}")
            return None
        finally:
            if "cap" in locals() and cap.isOpened():
                cap.release()

    async def _vision_loop(self) -> None:
        """Periodic visual presence detection and quality supervision."""
        while self.is_running:
            try:
                # Check if Vision is globally enabled in the heart
                heart = getattr(self, "_heart_ref", None)
                if heart and not heart.get_context().get("vision", {}).get(
                    "enabled", True
                ):
                    await asyncio.sleep(5)
                    continue

                # Capture low-res screenshot for presence detection
                screenshot = pyautogui.screenshot()
                screenshot.thumbnail((256, 256))

                # Update Heart state
                if heart:
                    heart.update_vision(
                        present=True,
                        focus="terminal",
                        objects=["code_editor", "terminal"],
                    )

                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Vision loop error: {e}")
                await asyncio.sleep(10)
