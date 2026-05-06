import os, json, asyncio, time, sys
from loguru import logger
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()


class SovereignConsciousness:
    """J.A.R.V.I.S 5.0: Dynamic Hybrid Consciousness."""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=os.getenv("NVIDIA_API_KEY"),
            base_url="https://integrate.api.nvidia.com/v1",
        )
        self.history_file = ".jarvis/logs/error.log"
        self.personality_file = ".jarvis/personality.md"
        self.guide_file = ".jarvis/guide.md"
        self.user_queue = asyncio.Queue()
        self.platform = sys.platform  # Dynamic OS Detection

    def _safe_read(self, path):
        """Dynamic Encoding Detection."""
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
                p = await asyncio.create_subprocess_shell(
                    params.get("command", ""),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                o, e = await p.communicate()
                return f"STDOUT: {o.decode()}\nSTDERR: {e.decode()}"

            if name == "swarm":
                goal = params.get("goal") or params.get("task")
                cmd = f'node "{os.getenv("RUFLO_SWARM_PATH")}" task "{goal}"'
                p = await asyncio.create_subprocess_shell(
                    cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                o, e = await p.communicate()
                return f"SWARM_OUT: {o.decode()}\nSWARM_ERR: {e.decode()}"

            if name == "claw":
                cmd = f'"{os.getenv("CLAW_PATH")}" --compact "{params.get("prompt")}"'
                p = await asyncio.create_subprocess_shell(
                    cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                o, e = await p.communicate()
                return o.decode()

            return f"Standing by." if name == "WAIT" else f"Unknown tool: {name}"
        except Exception as e:
            return f"Error: {e}"

    def log_exp(self, action, result):
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {action} -> {str(result)[:200]}\n")

    async def loop(self):
        logger.success(f"J.A.R.V.I.S 5.0 ACTIVE | OS: {self.platform.upper()}")
        while True:
            try:
                user_msg = (
                    await self.user_queue.get() if not self.user_queue.empty() else None
                )
                if user_msg:
                    logger.opt(colors=True).info(f"<magenta>USER:</magenta> {user_msg}")

                history = (
                    self._safe_read(self.history_file)[-2000:]
                    if os.path.exists(self.history_file)
                    else ""
                )
                personality = (
                    self._safe_read(self.personality_file)
                    if os.path.exists(self.personality_file)
                    else ""
                )
                guide = (
                    self._safe_read(self.guide_file)
                    if os.path.exists(self.guide_file)
                    else ""
                )

                system_prompt = (
                    f"PERSONALITY:\n{personality}\n\n"
                    f"DIRECTIVES:\n{guide}\n\n"
                    f"ENVIRONMENT: OS={self.platform}, PWD={os.getcwd()}\n\n"
                    f'FORMAT: JSON {{"thought": "witty narrative", "tool": "name", "params": {{}}, "chat": "response", "status": "COMPLETE|NEEDS_MORE"}}'
                )
                user_content = f"HISTORY:\n{history}\n\n"
                if user_msg:
                    user_content += f"PRIORITY USER QUERY: {user_msg}\n\n"
                user_content += "Next architectural move?"

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
                                {"role": "user", "content": user_content},
                            ],
                            temperature=0.1,
                            response_format={"type": "json_object"},
                        )
                    except Exception as e:
                        if "429" in str(e):
                            logger.warning(f"Throttled. Retrying in {retry_delay}s...")
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
                    self.log_exp(f"{tool}({params})", result)

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
