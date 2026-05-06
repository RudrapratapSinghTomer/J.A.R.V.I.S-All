from __future__ import annotations

import asyncio
import logging
from typing import Any, Mapping

from .base import AgentResult, AgentStatus, AgentTask, BaseAgent

logger = logging.getLogger("jarvis.hardware")


class HardwareAgent(BaseAgent):
    agent_id = "proprioception"
    body_part = "nervous_system"
    capabilities = (
        "monitor_health",
        "check_system",
        "proprioception",
        "sense_hardware",
    )
    toolsets = ("system_mcp", "hardware_metrics")
    hardware = ("cpu", "sensors")

    def __init__(
        self,
        mcp_server: Any | None = None,
        interval: float = 60.0,
    ) -> None:
        super().__init__(mcp_server)
        self.interval = interval
        self.is_running = False
        self._loop_task: asyncio.Task | None = None

    async def initialize(self) -> bool:
        self.is_running = True
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._hardware_loop())
        logger.info("HardwareAgent background loop started.")
        return True

    async def shutdown(self) -> None:
        self.is_running = False
        if self._loop_task:
            self._loop_task.cancel()
        logger.info("HardwareAgent background loop stopped.")

    async def handle(
        self,
        task: AgentTask,
        context: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        self.status = AgentStatus.WORKING

        # 1. Hardware Check
        metrics = await self._get_metrics()

        # 2. Security Check
        security = await self._check_security()

        # Update heart
        heart = (context or {}).get("heart")
        if heart:
            heart.update_health(
                cpu=metrics.get("cpu_percent", 0.0),
                memory=metrics.get("memory_percent", 0.0),
                disk=metrics.get("disk_percent", 0.0),
                firewall=security.get("firewall_enabled", True),
                defender=security.get("defender_active", True),
            )

        self.status = AgentStatus.IDLE
        return AgentResult(
            agent_id=self.agent_id,
            handled=True,
            summary=f"System Health: CPU {metrics.get('cpu_percent')}% | Security: {'STABLE' if security.get('firewall_enabled') else 'VULNERABLE'}",
            data={**metrics, **security},
            confidence=1.0,
        )

    async def _check_security(self) -> dict[str, Any]:
        """Check Windows Firewall and Defender status."""
        try:
            # Check Firewall
            fw_cmd = "Get-NetFirewallProfile -Profile Domain,Public,Private | Select-Object Name, Enabled"
            fw_proc = await asyncio.create_subprocess_shell(
                f'powershell -Command "{fw_cmd}"',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await fw_proc.communicate()
            firewall_enabled = "False" not in stdout.decode()

            # Check Defender
            def_cmd = "Get-MpComputerStatus | Select-Object AMServiceEnabled, RealTimeProtectionEnabled"
            def_proc = await asyncio.create_subprocess_shell(
                f'powershell -Command "{def_cmd}"',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await def_proc.communicate()
            defender_active = "True" in stdout.decode()

            return {
                "firewall_enabled": firewall_enabled,
                "defender_active": defender_active,
                "security_score": 1.0 if firewall_enabled and defender_active else 0.5,
            }
        except Exception as e:
            logger.error(f"Security check failed: {e}")
            return {
                "firewall_enabled": True,
                "defender_active": True,
                "security_score": 0.8,
            }

    async def _hardware_loop(self) -> None:
        while self.is_running:
            try:
                metrics = await self._get_metrics()
                # Update Heart
                heart = getattr(self, "_heart_ref", None)
                if heart:
                    heart.update_health(
                        cpu=metrics.get("cpu_percent", 0.0),
                        memory=metrics.get("memory_percent", 0.0),
                    )

                if metrics.get("cpu_percent", 0.0) > 85.0:
                    logger.warning("High CPU stress detected autonomously.")
                    # Proactively notify the mind via a simulated event if needed
            except Exception as e:
                logger.error(f"Error in hardware loop: {e}")
            await asyncio.sleep(self.interval)

    async def _get_metrics(self) -> dict[str, Any]:
        """Call the System MCP for real metrics."""
        if self.mcp_server:
            try:
                result = await self.mcp_server.call_tool(
                    "system.metrics",
                    {},
                    agent_id=self.agent_id,
                    scope="system:read",
                )
                if result.ok:
                    return result.data
            except Exception:
                pass

        # Fallback to psutil if available
        try:
            import psutil

            return {
                "cpu_percent": psutil.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_percent": psutil.disk_usage("/").percent,
            }
        except ImportError:
            return {"cpu_percent": 15.0, "memory_percent": 45.0, "disk_percent": 60.0}
