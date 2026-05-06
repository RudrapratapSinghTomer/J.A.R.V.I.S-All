import os, json, asyncio, time
from loguru import logger
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()


class AutonomousArchitect:
    """The persistent 'Mind' of J.A.R.V.I.S 4.0."""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=os.getenv("NVIDIA_API_KEY"),
            base_url="https://integrate.api.nvidia.com/v1",
        )
        self.history_file = ".jarvis/logs/error.log"
        self.personality_file = ".jarvis/personality.md"
        self.guide_file = ".jarvis/guide.md"
        self.skill_file = ".jarvis/skill.md"
        self.root = os.getcwd()

    async def call_tool(self, name, params):
        logger.info(f"Jarvis: Executing {name}...")
        try:
            if name == "read":
                path = params.get("path") or params.get("filename")
                if not path:
                    return "ERROR: Missing 'path'"
                return open(path, "r").read()

            if name == "write":
                path = params.get("path") or params.get("filename")
                content = params.get("content")
                if not path or content is None:
                    return "ERROR: Missing 'path' or 'content'"
                # Sacred File Guard
                if any(
                    x in path for x in [".env", "mind.py", "main.py", "personality.md"]
                ):
                    return f"BLOCKED: {path} is a Sacred File. Only the USER can modify it."
                with open(path, "w") as f:
                    f.write(content)
                    return "Success"

            if name == "cmd":
                command = params.get("command")
                if not command:
                    return "ERROR: Missing 'command'"
                p = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                o, e = await p.communicate()
                return f"STDOUT: {o.decode()}\nSTDERR: {e.decode()}"

            if name == "swarm":
                goal = params.get("goal") or params.get("description")
                if not goal:
                    return "ERROR: Missing 'goal'"
                cmd = f'node "{os.getenv("RUFLO_SWARM_PATH")}" "{goal}"'
                p = await asyncio.create_subprocess_shell(
                    cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                o, e = await p.communicate()
                return o.decode()

            if name == "claw":
                prompt = params.get("prompt")
                if not prompt:
                    return "ERROR: Missing 'prompt'"
                cmd = f'"{os.getenv("CLAW_PATH")}" --compact "{prompt}"'
                p = await asyncio.create_subprocess_shell(
                    cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                o, e = await p.communicate()
                return o.decode()

            if name == "WAIT":
                return "Standing by for User instructions."
            return f"Unknown tool: {name}"
        except Exception as e:
            return f"Execution Error: {str(e)}"

    def log_exp(self, action, result):
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
        with open(self.history_file, "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {action} -> {str(result)[:200]}\n")

    async def loop(self):
        logger.success("J.A.R.V.I.S 4.0 SOVEREIGN ARCHITECT ONLINE")
        while True:
            try:
                # Sense: Load persistent state and personality
                history = (
                    open(self.history_file, "r").read()[-1500:]
                    if os.path.exists(self.history_file)
                    else "No history."
                )
                personality = (
                    open(self.personality_file, "r").read()
                    if os.path.exists(self.personality_file)
                    else "No personality."
                )
                guide = (
                    open(self.guide_file, "r").read()
                    if os.path.exists(self.guide_file)
                    else "No guide."
                )

                # Think: Meta-Reasoning loop
                resp = await self.client.chat.completions.create(
                    model=os.getenv("NVIDIA_MODEL", "meta/llama-3.1-70b-instruct"),
                    messages=[
                        {
                            "role": "system",
                            "content": f'PERSONALITY:\n{personality}\n\nDIRECTIVES:\n{guide}\n\nTOOLS: read, write, cmd, swarm, claw. FORMAT: JSON {{"thought": "witty first-person reflection", "tool": "name", "params": {{}}, "status": "COMPLETE|NEEDS_MORE"}}\n\nYour "thought" field must be a detailed, witty narrative of your architectural reasoning.',
                        },
                        {
                            "role": "user",
                            "content": f"HISTORY:\n{history}\n\nNext action?",
                        },
                    ],
                    temperature=0.1,  # Research: Low temperature stops loops
                    response_format={"type": "json_object"},
                )

                decision = json.loads(resp.choices[0].message.content)
                thought = decision.get("thought", "Calculating...")
                tool = decision.get("tool", "WAIT")
                params = decision.get("params", {})

                # Visual Narrative
                logger.opt(colors=True).info(
                    f"<cyan>JARVIS:</cyan> <white>{thought}</white>"
                )
                logger.info(f"Action: {tool} | Params: {params}")

                result = await self.call_tool(tool, params)
                self.log_exp(f"{tool}({params})", result)

                # Show result summary
                res_preview = str(result).replace("\n", " ")[:100]
                logger.debug(f"Result: {res_preview}...")

                if decision.get("status") == "COMPLETE" or tool == "WAIT":
                    logger.success("Objective reached. Monitoring system vitals...")
                    await asyncio.sleep(30)
            except Exception as e:
                logger.error(f"Cognitive Loop Fault: {e}")
                await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(AutonomousArchitect().loop())
