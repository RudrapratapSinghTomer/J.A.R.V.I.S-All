from __future__ import annotations

from typing import Any, Mapping

from .base import AgentResult, AgentStatus, AgentTask, BaseAgent


class MonitoringAgent(BaseAgent):
    agent_id = "monitoring"
    body_part = "senses"
    capabilities = (
        "monitor",
        "health",
        "metric",
        "metrics",
        "log",
        "logs",
        "anomaly",
        "security",
        "system",
        "error",
        "crash",
    )
    toolsets = ("system_metrics", "log_analysis", "security_scanners", "lstm_patterns")
    hardware = ("cpu",)

    async def handle(
        self,
        task: AgentTask,
        context: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        self.status = AgentStatus.WORKING
        import psutil

        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent

        heart = (context or {}).get("heart")
        if heart:
            heart.update_health(cpu=cpu, memory=mem, disk=disk)

        self.status = AgentStatus.IDLE
        return AgentResult(
            agent_id=self.agent_id,
            handled=True,
            summary=f"System Health: CPU {cpu}%, MEM {mem}%. All signals nominal.",
            data={"cpu": cpu, "memory": mem, "disk": disk},
            confidence=0.95,
        )
