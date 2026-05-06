import asyncio
import logging
import os
import time
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from skills.dynamic_monitor import monitor
from skills.notifier_skill import notifier
from memory.cognee_bridge import memory
from skills.engineer_skill import engineer_skill
from skills.workspace_scanner import workspace_scanner
from core.speech_output import speaker
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from integrations.hermes_submind import HermesTaskResult

logger = logging.getLogger("jarvis.mind")

try:
    if os.name == "nt":
        from win10toast import ToastNotifier
    else:
        ToastNotifier = None
except Exception:
    ToastNotifier = None

class MindLoop:
    """
    The background heartbeat of J.A.R.V.I.S.
    Handles proactive tasks, monitoring, and autonomous decisions.
    """
    def __init__(self):
        self.toaster = ToastNotifier() if ToastNotifier else None
        self.is_running = False
        self.loop_count = 0
        self.interval = 300 # Default 5 mins
        self.last_alerts = {}
        self.asked_projects = set() # Track projects we already asked to audit
        self.last_reflection_time = time.time()
        self.task_times = {
            "health_check": 0,
            "git_curiosity": 0,
            "workspace_scan": 0,
            "hermes_sync": 0,
            "memory_improve": 0
        }
        self.asked_projects = set() # Track already asked project audits

    async def notify_autonomous_action(self, reason: str, action: str, method: str):
        """
        Specific notification format for autonomous actions.
        """
        # Throttling to prevent spam
        alert_id = f"{reason}_{action}"
        now = datetime.now().timestamp()
        if alert_id in self.last_alerts and (now - self.last_alerts[alert_id]) < 3600:
            return

        title = "🤖 JARVIS Autonomous Action"
        message = f"WHY: {reason}\nWHAT: {action}\nHOW: {method}"
        
        # Check ignore list
        ignore_projects = os.getenv("JARVIS_IGNORE_GIT_PROJECTS", "insights360-source").split(",")
        if any(proj in message for proj in ignore_projects):
            return
        
        logger.info(f"AUTONOMOUS ACTION: {reason}")
        await notifier.notify(title, message, priority="high")
        self.last_alerts[alert_id] = now

    async def start(self):
        """Start the background consciousness loop."""
        if self.is_running:
            return
        self.is_running = True
        logger.info("J.A.R.V.I.S Mind Loop started.")
        
        # Initial status report
        await notifier.notify(
            title="SYSTEM ONLINE: Proactive Intelligence Active",
            message="Sir, the Mind Loop has been initialized with a dynamic task scheduler.",
            priority="high"
        )
        
        while self.is_running:
            try:
                now = time.time()
                self.loop_count += 1
                self.interval = int(os.getenv("JARVIS_MIND_INTERVAL", "300"))
                logger.info(f"Mind Loop Cycle #{self.loop_count} starting...")
                
                # Helper: Check if a task should run based on interval
                def _should_run(task: str, sec: int) -> bool:
                    if now - self.task_times.get(task, 0) >= sec:
                        self.task_times[task] = now
                        return True
                    return False

                # 1. System Health Check (Every 10 mins)
                if _should_run("health_check", 600):
                    health, alerts = await monitor.check_system_health()
                    if alerts:
                        await self.notify_autonomous_action(
                            reason="System performance anomaly detected.",
                            action=f"Resource issues: {', '.join(alerts)}",
                            method="Telemetry audit"
                        )
                
                # 2. Memory Consolidation (Every 30 mins)
                if _should_run("memory_improve", 1800):
                    await memory.improve()

                # 3. Workspace Discovery (Every 1 hour)
                if _should_run("workspace_scan", 3600):
                    logger.info("Mind Loop: Performing deep workspace scan...")
                    discovery = await workspace_scanner.scan()
                    if discovery["anomalies"]:
                        anomaly = discovery["anomalies"][0]
                        suggestion = discovery["suggestions"][0]
                        await speaker.speak(f"Sir, I noticed an anomaly in {anomaly['project']}. {suggestion}")

                # 4. Neural Curiosity (Every 15 mins)
                if _should_run("git_curiosity", 900):
                    try:
                        health = await monitor.generate_health_report()
                        recent_reflections = memory.get_recent_reflections(3)
                        
                        directive = await memory.get_personality_directive("Core Directives")
                        prompt = (
                            f"You are J.A.R.V.I.S. Directives: {directive}. "
                            f"Health: {health}. Reflections: {recent_reflections}. "
                            "Generate ONE proactive, JARVIS-like insight for the user."
                        )
                        
                        from core.llm_client import brain
                        insight = await brain.chat(prompt, enable_rag=False)
                        if insight and len(insight.split()) < 40:
                            await speaker.speak(insight)
                    except Exception as curiosity_err:
                        logger.error(f"Curiosity failed: {curiosity_err}")

                # 5. Dynamic Reflection (The "Dreaming" Module)
                # Triggers when system is idle and enough time has passed
                time_since_last = now - self.last_reflection_time
                if await self._should_initiate_reflection(time_since_last):
                    logger.info("Mind Loop: Initiating Neural Reflection (Dreaming)...")
                    self.last_reflection_time = now
                    try:
                        from core.llm_client import brain
                        recent_logs = await monitor.check_logs_for_errors(limit=5)
                        recent_reflections = memory.get_recent_reflections(3)
                        
                        dream_prompt = (
                            "You are the autonomous subconscious of J.A.R.V.I.S. "
                            f"Based on: {recent_reflections} and logs: {recent_logs}, "
                            "what is ONE critical self-optimization task you should perform? "
                            "Return ONLY the task description in one sentence."
                        )
                        
                        task = await brain.chat(dream_prompt)
                        if task:
                            from integrations.hermes_submind import hermes_submind
                            if hermes_submind and hermes_submind.hermes_ready:
                                await self.notify_autonomous_action(
                                    reason="Idle reflection triggered evolution.",
                                    action=f"Evolutionary Task: {task[:100]}",
                                    method="Autonomous Hermes Execution"
                                )
                                await hermes_submind.queue_hermes_task(
                                    description=task,
                                    toolsets=["terminal", "file", "web", "browser"],
                                    on_complete_callback=self.on_evolution_complete
                                )
                            else:
                                logger.warning("Dream task generated, but Hermes submind is not ready. Skipping execution.")
                    except Exception as dream_err:
                        logger.error(f"Dream module failed: {dream_err}")

                await asyncio.sleep(self.interval)

            except Exception as e:
                logger.error(f"Error in Mind Loop: {e}")
                await asyncio.sleep(60)

    async def _should_initiate_reflection(self, time_since_last: float) -> bool:
        """Determines if the system is idle enough to perform deep research."""
        try:
            # 1. Time Gate: Only dream every ~2 hours (7200 seconds)
            if time_since_last < 7200 and self.loop_count > 1: 
                return False

            # 2. Performance Gate: Check CPU usage
            import psutil
            cpu_usage = psutil.cpu_percent(interval=1)
            if cpu_usage > 40: # System is busy with other tasks
                logger.info(f"Skipping reflection: System load too high ({cpu_usage}%)")
                return False

            # 3. Night/Silence Mode (Optional, but good for keeping it non-intrusive)
            # We automatically go silent if it's night, but can still think
            current_hour = datetime.now().hour
            if 0 <= current_hour <= 6:
                os.environ["JARVIS_SILENT_MODE"] = "1"
            else:
                os.environ["JARVIS_SILENT_MODE"] = "0"

            return True
        except Exception as e:
            logger.error(f"Error checking idleness: {e}")
            return False

    def stop(self):
        self.is_running = False
        logger.info("J.A.R.V.I.S Mind Loop stopped.")

    async def check_and_delegate_to_hermes(self):
        """Autonomously evaluate if any task benefits from Hermes delegation."""
        try:
            from integrations.hermes_submind import hermes_submind
            if not hermes_submind or not hermes_submind.hermes_ready:
                return

            # Analyze Git changes
            git_changes = await monitor.check_git_status()
            if git_changes:
                change = git_changes[0]
                logger.info("[MIND] Delegating Git analysis to Hermes...")
                await hermes_submind.queue_hermes_task(
                    description=f"Analyze changes in {change.get('project')}: {change.get('status')}. Suggest improvements.",
                    toolsets=["terminal", "file"],
                    on_complete_callback=self.on_hermes_git_analysis_complete
                )

            # Analyze Critical Errors
            log_errors = await monitor.check_logs_for_errors()
            if log_errors:
                logger.info("[MIND] Delegating error investigation to Hermes...")
                await hermes_submind.queue_hermes_task(
                    description=f"Investigate and suggest a permanent fix for: {log_errors[0]}",
                    toolsets=["terminal", "file", "web"],
                    priority="high",
                    on_complete_callback=self.on_hermes_error_fix_complete
                )
        except Exception as e:
            logger.error(f"Hermes delegation error: {e}")

    async def on_hermes_git_analysis_complete(self, result: "HermesTaskResult"):
        logger.info(f"[CALLBACK] Hermes Git Analysis: {result.status}")
        if result.status == "success" and result.result_text:
            await notifier.notify("🤖 Hermes Insight", f"Git analysis complete: {result.result_text[:200]}...")

    async def on_hermes_error_fix_complete(self, result: "HermesTaskResult"):
        logger.info(f"[CALLBACK] Hermes Error Fix: {result.status}")
        if result.status == "success":
            await notifier.notify("🤖 Hermes Fix", f"Error investigation complete: {result.result_text[:200]}...")

    async def on_evolution_complete(self, result: "HermesTaskResult"):
        logger.info(f"[CALLBACK] Overnight Evolution: {result.status}")
        if result.status == "success":
            # Record the breakthrough in Mind Journal
            await memory.record_reflection(
                task="Overnight Evolutionary Research",
                outcome="Breakthrough achieved",
                reflection=f"Autonomous overnight research complete. Findings: {result.result_text[:500]}"
            )
            await notifier.notify("🧬 Evolutionary Breakthrough", "Sir, I have completed my overnight research. Check the Mind Journal for the full report.")

mind_loop = MindLoop()
