import os, json, asyncio, time, sys
from loguru import logger
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()


class SequenceManager:
    """J.A.R.V.I.S 7.0 Sequence Controller: Detects patterns that lead to failure."""

    def __init__(self, memory_path=".jarvis/memory/sequences.json"):
        self.memory_path = memory_path
        self.current_seq = []
        self.failures = self._load()

    def _load(self):
        if os.path.exists(self.memory_path):
            try:
                with open(self.memory_path, "r") as f:
                    return json.load(f)
            except:
                return []
        return []

    def record(self, tool, status="SUCCESS"):
        self.current_seq.append(tool)
        if len(self.current_seq) > 5:
            self.current_seq.pop(0)
        if status == "FAILED":
            self.failures.append({"seq": list(self.current_seq), "ts": time.time()})
            os.makedirs(os.path.dirname(self.memory_path), exist_ok=True)
            with open(self.memory_path, "w") as f:
                json.dump(self.failures[-50:], f, indent=2)

    def check(self):
        for f in self.failures:
            if all(x in self.current_seq for x in f["seq"][-2:]):
                return f"CRITICAL ALERT: Your current action sequence matches a historical failure pattern! Proceed with caution."
        return ""


class SequenceArchitect:
    """J.A.R.V.I.S 7.0: Dynamic & Reflective Sovereign Architect."""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=os.getenv("NVIDIA_API_KEY"),
            base_url="https://integrate.api.nvidia.com/v1",
        )
        self.seq_manager = SequenceManager()
        self.history_file = ".jarvis/logs/error.log"
        self.personality_file = ".jarvis/personality.md"
        self.guide_file = ".jarvis/guide.md"
        self.user_queue = asyncio.Queue()
        self.platform = sys.platform  # Dynamic OS detection

    def _safe_read(self, path):
        """Dynamic Encoding Detection: Prevents 'charmap' crashes."""
        for enc in ["utf-8", "latin1", "cp1252", "utf-16"]:
            try:
                with open(path, "r", encoding=enc) as f:
                    return f.read()
            except:
                continue
        return open(path, "r", errors="replace").read()

    async def call_tool(self, name, params):
        try:
            if name == "read":
                path = params.get("path") or params.get("filename")
                return self._safe_read(path) if path else "ERROR: Missing path"

            if name == "write":
                path, content = params.get("path"), params.get("content")
                if any(x in str(path) for x in [".env", "mind.py", "main.py"]):
                    return "BLOCKED."
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                    return "Success"

            if name == "cmd":
                command = params.get("command", "")
                p = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                o, e = await p.communicate()
                status = "FAILED" if e else "SUCCESS"
                self.seq_manager.record("cmd", status)
                return f"STDOUT: {o.decode()}\nSTDERR: {e.decode()}"

            if name == "swarm":
                self.seq_manager.record("swarm")
                # Dynamic Swarm Command Construction
                goal = params.get("goal") or params.get("task")
                swarm_bin = os.getenv("RUFLO_SWARM_PATH")
                cmd = f'node "{swarm_bin}" task "{goal}"'  # Corrected syntax for ruflo/claude-flow
                p = await asyncio.create_subprocess_shell(
                    cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                o, e = await p.communicate()
                return f"SWARM_OUT: {o.decode()}\nSWARM_ERR: {e.decode()}"

            self.seq_manager.record(name)
            return "Standing by."
        except Exception as e:
            self.seq_manager.record(name, "FAILED")
            return f"Error: {e}"

    async def loop(self):
        logger.success(f"J.A.R.V.I.S 7.0 ONLINE | OS: {self.platform.upper()}")
        while True:
            try:
                user_msg = (
                    await self.user_queue.get() if not self.user_queue.empty() else None
                )
                if user_msg:
                    logger.opt(colors=True).info(f"<magenta>USER:</magenta> {user_msg}")

                history = (
                    self._safe_read(self.history_file)[-1500:]
                    if os.path.exists(self.history_file)
                    else ""
                )
                warning = self.seq_manager.check()
                personality = self._safe_read(self.personality_file)
                guide = self._safe_read(self.guide_file)

                # Dynamic System Prompt: Injects Environment Context to prevent OS-hallucinations
                system_prompt = (
                    f"PERSONALITY:\n{personality}\n\n"
                    f"DIRECTIVES:\n{guide}\n\n"
                    f"ENVIRONMENT: OS={self.platform}, SHELL=powershell, PWD={os.getcwd()}\n"
                    f"{warning}\n\n"
                    f'FORMAT: JSON {{"thought": "witty narrative", "tool": "name", "params": {{}}, "chat": "response", "status": "COMPLETE|NEEDS_MORE"}}'
                )

                resp = None
                retry_delay = 10
                while not resp:
                    try:
                        resp = await self.client.chat.completions.create(
                            model=os.getenv(
                                "NVIDIA_MODEL", "meta/llama-3.1-70b-instruct"
                            ),
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {
                                    "role": "user",
                                    "content": f"INPUT: {user_msg}\nMove?"
                                    if user_msg
                                    else "Autonomous loop.",
                                },
                            ],
                            temperature=0.1,
                            response_format={"type": "json_object"},
                        )
                    except Exception as e:
                        if "429" in str(e):
                            logger.warning(f"Rate limited. Waiting {retry_delay}s...")
                            await asyncio.sleep(retry_delay)
                            retry_delay = min(retry_delay * 2, 60)
                        else:
                            raise e

                decision = json.loads(resp.choices[0].message.content)
                if decision.get("chat"):
                    logger.opt(colors=True).info(
                        f"<cyan>JARVIS:</cyan> <white>{decision['chat']}</white>"
                    )
                logger.opt(colors=True).info(
                    f"<blue>THOUGHT:</blue> {decision.get('thought')}"
                )

                tool, params = decision.get("tool"), decision.get("params", {})
                if tool and tool != "WAIT":
                    result = await self.call_tool(tool, params)
                    with open(self.history_file, "a", encoding="utf-8") as f:
                        f.write(
                            f"[{time.strftime('%H:%M:%S')}] {tool} -> {str(result)[:100]}\n"
                        )

                # Interruptible Sleep
                if not user_msg:
                    try:
                        incoming = await asyncio.wait_for(
                            self.user_queue.get(), timeout=25
                        )
                        await self.user_queue.put(incoming)
                    except asyncio.TimeoutError:
                        pass
            except Exception as e:
                logger.error(f"Fault: {e}")
                await asyncio.sleep(10)
