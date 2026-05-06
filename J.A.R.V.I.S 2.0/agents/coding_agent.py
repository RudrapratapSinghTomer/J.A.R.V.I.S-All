from __future__ import annotations
import re
from typing import Any, Mapping
from .base import AgentResult, AgentStatus, AgentTask, BaseAgent
from core.llm_client import ModelCapability, require_capability


class CodingAgent(BaseAgent):
    agent_id = "coding"
    body_part = "hands"
    capabilities = (
        "code",
        "coding",
        "bug",
        "fix",
        "refactor",
        "github",
        "terminal",
        "project",
        "audit",
        "test",
        "build",
    )
    toolsets = ("github", "file_system", "terminal", "git", "mcp_coding_tools")
    hardware = ("cpu", "cloud")

    def __init__(
        self, mcp_server: Any | None = None, llm_client: Any | None = None
    ) -> None:
        super().__init__(mcp_server)
        self.llm_client = llm_client

    @require_capability(ModelCapability.CODING)
    async def handle(
        self,
        task: AgentTask,
        context: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        self.status = AgentStatus.WORKING
        content = task.content.strip()
        lower = content.lower()
        actions: list[dict[str, Any]] = []

        if not self.mcp_server:
            self.status = AgentStatus.IDLE
            return AgentResult(
                agent_id=self.agent_id,
                handled=False,
                summary="Coding tools are unavailable because MCP server is missing.",
                data={"status": "failed", "error": "missing_mcp_server"},
                confidence=0.2,
            )

        try:
            if "github" in lower:
                actions.extend(await self._handle_github_request(content))
            else:
                actions.extend(await self._handle_file_request(content))

            successful = [a for a in actions if a.get("ok")]
            failed = [a for a in actions if not a.get("ok")]
            status = "success" if successful and not failed else "failed"
            summary = (
                f"Executed {len(successful)} coding action(s)."
                if status == "success"
                else f"Completed with {len(failed)} failed action(s)."
            )
            data = {"status": status, "actions": actions}
            handled = bool(successful)
            confidence = 0.92 if status == "success" else 0.35
        except Exception as e:
            summary = f"Coding execution failed: {e}"
            data = {"status": "failed", "error": str(e), "actions": actions}
            handled = False
            confidence = 0.2

        self.status = AgentStatus.IDLE
        return AgentResult(
            agent_id=self.agent_id,
            handled=handled,
            summary=summary,
            data=data,
            confidence=confidence,
        )

    async def _handle_file_request(self, content: str) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        
        # 1. Intelligent Action Extraction
        if self.llm_client:
            prompt = (
                "You are the Action Controller for J.A.R.V.I.S. 2.0. Map the user request to a list of MCP tool calls.\n"
                "Available tools:\n"
                "- file_system.list(path: str)\n"
                "- file_system.read(path: str)\n"
                "- file_system.write(path: str, content: str, mode: 'overwrite'|'append')\n"
                "- github.get_profile()\n"
                "- github.update_profile(name?: str, bio?: str, dry_run?: bool)\n\n"
                f"Request: \"{content}\"\n"
                "Output ONLY a JSON list of calls: [{\"tool\": \"name\", \"args\": {}}]"
            )
            try:
                response = await self.llm_client.generate(
                    prompt, ModelCapability.UTILITY, purpose="action_extraction"
                )
                import json
                # Clean response (remove markdown blocks if present)
                text = response.text.strip()
                if text.startswith("```json"):
                    text = text[7:-3].strip()
                elif text.startswith("```"):
                    text = text[3:-3].strip()
                
                match = re.search(r"\[.*\]", text, re.DOTALL)
                if match:
                    calls = json.loads(match.group())
                    for call in calls:
                        tool_name = call.get("tool")
                        args = call.get("args", {})
                        
                        # Execute tool
                        scope = "system:write" if any(x in tool_name for x in ("write", "update", "create")) else "system:read"
                        result = await self.mcp_server.call_tool(
                            tool_name,
                            args,
                            agent_id=self.agent_id,
                            scope=scope,
                        )
                        actions.append({
                            "tool": tool_name,
                            "ok": result.ok,
                            "path": args.get("path"),
                            "result": result.data,
                            "error": result.error,
                        })
                    if actions:
                        return actions
            except Exception as e:
                logger.error(f"Intelligent action extraction failed: {e}", exc_info=True)
                # We fall through to legacy regex if LLM synthesis fails

        # 2. Brittle Fallback (Legacy Regex)
        create_match = re.search(r"(?:create|make)\s+file\s+([^\s]+)", content, re.IGNORECASE)
        if create_match:
            path = create_match.group(1).strip().strip("\"'")
            res = await self.mcp_server.call_tool("file_system.write", {"path": path, "content": ""}, agent_id=self.agent_id, scope="system:write")
            actions.append({"tool": "file_system.write", "ok": res.ok, "path": path, "result": res.data, "error": res.error})
            return actions

        read_match = re.search(r"(?:read|open|look|refer)\s+(?:to\s+)?(?:file\s+)?([^\s]+\.[a-z0-9]+)", content, re.IGNORECASE)
        if read_match:
            path = read_match.group(1).strip().strip("\"'")
            res = await self.mcp_server.call_tool("file_system.read", {"path": path}, agent_id=self.agent_id, scope="system:read")
            actions.append({"tool": "file_system.read", "ok": res.ok, "path": path, "result": res.data, "error": res.error})
            return actions

        res = await self.mcp_server.call_tool("file_system.list", {"path": "."}, agent_id=self.agent_id, scope="system:read")
        actions.append({"tool": "file_system.list", "ok": res.ok, "path": ".", "result": res.data, "error": res.error})
        return actions

    async def _handle_github_request(self, content: str) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        lower = content.lower()
        if "update" in lower and "profile" in lower:
            bio_match = re.search(r"bio\s+(?:to|as)\s+(.+)$", content, re.IGNORECASE)
            payload: dict[str, Any] = {"dry_run": True}
            if bio_match:
                payload["bio"] = bio_match.group(1).strip().strip("\"'")
            else:
                payload["bio"] = "Updated by J.A.R.V.I.S. 2.0"
            update_result = await self.mcp_server.call_tool(
                "github.update_profile",
                payload,
                agent_id=self.agent_id,
                scope="system:write",
            )
            actions.append(
                {
                    "tool": "github.update_profile",
                    "ok": update_result.ok,
                    "result": update_result.data,
                    "error": update_result.error,
                }
            )

        profile_result = await self.mcp_server.call_tool(
            "github.get_profile",
            {},
            agent_id=self.agent_id,
            scope="system:read",
        )
        actions.append(
            {
                "tool": "github.get_profile",
                "ok": profile_result.ok,
                "result": profile_result.data,
                "error": profile_result.error,
            }
        )
        return actions
