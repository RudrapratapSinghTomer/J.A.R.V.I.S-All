import os, json, asyncio, time, sys
from loguru import logger
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()


class ReflectiveArchitect:
    """J.A.R.V.I.S 6.0: Dynamic Reflective Architect."""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=os.getenv("NVIDIA_API_KEY"),
            base_url="https://integrate.api.nvidia.com/v1",
        )
        self.history_file = ".jarvis/logs/error.log"
        self.ledger_file = ".jarvis/memory/wisdom_ledger.json"
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

    async def reflect(self, action, error):
        logger.warning(f"Reflecting on: {action}")
        prompt = f'FAILURE ANALYSIS:\nAction: {action}\nError: {error}\n\nExtract a \'System Note\'. FORMAT: JSON {{"trigger": "condition", "prevention": "rule"}}'
        try:
            resp = await self.client.chat.completions.create(
                model=os.getenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct"),
                messages=[
                    {
                        "role": "system",
                        "content": "You are the J.A.R.V.I.S Archivist. Extract architectural lessons.",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
            )
            lesson = json.loads(resp.choices[0].message.content)
            ledger = []
            if os.path.exists(self.ledger_file):
                with open(self.ledger_file, "r") as f:
                    ledger = json.load(f)
            ledger.append(lesson)
            os.makedirs(os.path.dirname(self.ledger_file), exist_ok=True)
            with open(self.ledger_file, "w") as f:
                json.dump(ledger[-20:], f, indent=2)
            return lesson
        except Exception as e:
            return {"error": str(e)}

    async def call_tool(self, name, params):
        try:
            if name == "read":
                return self._safe_read(params.get("path"))
            if name == "write":
                if any(
                    x in str(params.get("path")) for x in [".env", "mind.py", "main.py"]
                ):
                    return "BLOCKED."
                with open(params["path"], "w", encoding="utf-8") as f:
                    f.write(params["content"])
                    return "Success"
            if name == "cmd":
                p = await asyncio.create_subprocess_shell(
                    params.get("command", ""),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                o, e = await p.communicate()
                res = f"STDOUT: {o.decode()}\nSTDERR: {e.decode()}"
                if e:
                    await self.reflect(params["command"], res)
                return res
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
            return "Standing by."
        except Exception as e:
            await self.reflect(f"{name}({params})", str(e))
            return f"Error: {e}"

    def log_exp(self, action, result):
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {action} -> {str(result)[:100]}\n")

    async def loop(self):
        logger.success(f"J.A.R.V.I.S 6.0 ACTIVE | OS: {self.platform.upper()}")
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
                ledger = (
                    self._safe_read(self.ledger_file)
                    if os.path.exists(self.ledger_file)
                    else "[]"
                )
                personality = self._safe_read(self.personality_file)
                guide = self._safe_read(self.guide_file)

                system_prompt = (
                    f"PERSONALITY:\n{personality}\n\n"
                    f"DIRECTIVES:\n{guide}\n\n"
                    f"ENVIRONMENT: OS={self.platform}, PWD={os.getcwd()}\n\n"
                    f"WISDOM LEDGER (LTM):\n{ledger}\n\n"
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
                                    "content": f"INPUT: {user_msg}\nNext?"
                                    if user_msg
                                    else "Autonomous.",
                                },
                            ],
                            temperature=0.1,
                            response_format={"type": "json_object"},
                        )
                    except Exception as e:
                        if "429" in str(e):
                            logger.warning(f"Throttled. Waiting {retry_delay}s...")
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
