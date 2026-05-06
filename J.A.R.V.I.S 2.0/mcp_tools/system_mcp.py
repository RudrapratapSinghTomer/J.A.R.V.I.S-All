from __future__ import annotations

import asyncio
import inspect
import json
import os
import platform
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib import error, request


ToolHandler = Callable[[dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class MCPTool:
    name: str
    description: str
    scopes: tuple[str, ...]
    handler: ToolHandler
    agent_safe: bool = True


@dataclass(frozen=True)
class MCPToolResult:
    ok: bool
    tool: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True)
class MCPToolCall:
    tool: str
    payload: dict[str, Any]
    agent_id: str
    scope: str


class SystemMCPServer:
    """Small MCP-style registry for safe multi-agent system tools."""

    def __init__(
        self,
        max_concurrent_calls: int = 8,
        project_root: str | Path | None = None,
    ) -> None:
        self.tools: dict[str, MCPTool] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent_calls)
        self._event_log: list[dict[str, Any]] = []
        self.project_root = Path(project_root or Path.cwd()).resolve()

    def register_tool(
        self,
        name: str,
        description: str,
        scopes: tuple[str, ...],
        handler: ToolHandler,
        *,
        agent_safe: bool = True,
    ) -> None:
        self.tools[name] = MCPTool(
            name=name,
            description=description,
            scopes=scopes,
            handler=handler,
            agent_safe=agent_safe,
        )

    async def call_tool(
        self,
        tool_name: str,
        payload: dict[str, Any],
        *,
        agent_id: str,
        scope: str,
    ) -> MCPToolResult:
        tool = self.tools.get(tool_name)
        if tool is None:
            return MCPToolResult(ok=False, tool=tool_name, error="tool_not_found")
        if scope not in tool.scopes and "*" not in tool.scopes:
            return MCPToolResult(ok=False, tool=tool_name, error="scope_denied")
        if not tool.agent_safe:
            return MCPToolResult(ok=False, tool=tool_name, error="tool_not_agent_safe")

        async with self._semaphore:
            try:
                value = tool.handler({**payload, "agent_id": agent_id})
                data = await value if inspect.isawaitable(value) else value
                return MCPToolResult(ok=True, tool=tool_name, data=data)
            except Exception as exc:  # pragma: no cover - defensive boundary.
                return MCPToolResult(ok=False, tool=tool_name, error=str(exc))

    async def call_many(self, calls: list[MCPToolCall]) -> list[MCPToolResult]:
        return await asyncio.gather(
            *(
                self.call_tool(
                    call.tool,
                    call.payload,
                    agent_id=call.agent_id,
                    scope=call.scope,
                )
                for call in calls
            )
        )

    def describe_tools(self) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "description": tool.description,
                "scopes": list(tool.scopes),
                "agent_safe": tool.agent_safe,
            }
            for name, tool in self.tools.items()
        }

    def _metrics(self, payload: dict[str, Any]) -> dict[str, Any]:
        usage = shutil.disk_usage(Path.cwd())
        return {
            "agent_id": payload.get("agent_id"),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
            "cwd": str(Path.cwd()),
            "disk": {
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
            },
        }

    def _log_event(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._event_log.append(payload)
        return {"event_count": len(self._event_log), "last_event": payload}

    @staticmethod
    def _echo(payload: dict[str, Any]) -> dict[str, Any]:
        return {"echo": payload}

    def _resolve_workspace_path(self, target: str) -> Path:
        requested = Path(target)
        candidate = (
            requested
            if requested.is_absolute()
            else (self.project_root / requested).resolve()
        )
        resolved = candidate.resolve()
        if not str(resolved).startswith(str(self.project_root)):
            raise ValueError("path_outside_project_root")
        return resolved

    def _file_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        relative_path = str(payload.get("path") or ".")
        directory = self._resolve_workspace_path(relative_path)
        if not directory.exists():
            raise FileNotFoundError("path_not_found")
        if not directory.is_dir():
            raise NotADirectoryError("path_not_directory")
        items: list[dict[str, Any]] = []
        for item in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
            items.append(
                {
                    "name": item.name,
                    "path": str(item.relative_to(self.project_root)),
                    "is_dir": item.is_dir(),
                    "size": item.stat().st_size if item.is_file() else None,
                }
            )
        return {
            "path": str(directory.relative_to(self.project_root)),
            "items": items,
            "count": len(items),
        }

    def _file_read(self, payload: dict[str, Any]) -> dict[str, Any]:
        relative_path = str(payload.get("path") or "")
        if not relative_path:
            raise ValueError("missing_path")
        file_path = self._resolve_workspace_path(relative_path)
        if not file_path.exists():
            raise FileNotFoundError("path_not_found")
        if not file_path.is_file():
            raise IsADirectoryError("path_not_file")
        text = file_path.read_text(encoding="utf-8")
        return {
            "path": str(file_path.relative_to(self.project_root)),
            "content": text,
            "bytes": file_path.stat().st_size,
        }

    def _file_write(self, payload: dict[str, Any]) -> dict[str, Any]:
        relative_path = str(payload.get("path") or "")
        if not relative_path:
            raise ValueError("missing_path")
        file_path = self._resolve_workspace_path(relative_path)
        content = str(payload.get("content", ""))
        mode = str(payload.get("mode", "overwrite")).lower()
        file_path.parent.mkdir(parents=True, exist_ok=True)

        if mode == "append":
            with file_path.open("a", encoding="utf-8") as handle:
                handle.write(content)
        else:
            file_path.write_text(content, encoding="utf-8")
        return {
            "path": str(file_path.relative_to(self.project_root)),
            "bytes": file_path.stat().st_size,
            "mode": mode,
        }

    @staticmethod
    def _github_headers(token: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "jarvis-2.0-system-mcp",
            "Content-Type": "application/json",
        }

    def _github_request(
        self,
        method: str,
        endpoint: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = os.getenv("JARVIS_GITHUB_TOKEN")
        if not token:
            raise RuntimeError("github_token_missing")
        url = f"https://api.github.com{endpoint}"
        data: bytes | None = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")

        req = request.Request(
            url,
            data=data,
            method=method.upper(),
            headers=self._github_headers(token),
        )
        try:
            with request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {}
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"github_http_{exc.code}:{detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"github_connection_error:{exc.reason}") from exc

    def _github_get_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        _ = payload
        data = self._github_request("GET", "/user")
        return {
            "login": data.get("login"),
            "name": data.get("name"),
            "html_url": data.get("html_url"),
            "bio": data.get("bio"),
            "public_repos": data.get("public_repos"),
        }

    def _github_update_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        dry_run = bool(payload.get("dry_run", False))
        update_body: dict[str, Any] = {}
        for key in ("name", "company", "blog", "location", "hireable", "bio"):
            if key in payload and payload[key] is not None:
                update_body[key] = payload[key]
        if not update_body:
            raise ValueError("missing_profile_fields")

        if dry_run:
            return {"dry_run": True, "payload": update_body}

        data = self._github_request("PATCH", "/user", payload=update_body)
        return {
            "dry_run": False,
            "html_url": data.get("html_url"),
            "name": data.get("name"),
            "bio": data.get("bio"),
        }


def create_default_system_mcp(project_root: str | Path | None = None) -> SystemMCPServer:
    server = SystemMCPServer(project_root=project_root)
    server.register_tool(
        "system.metrics",
        "Read-only system metrics for health checks.",
        ("system:read",),
        server._metrics,
    )
    server.register_tool(
        "system.log_event",
        "Store an in-memory event for agent coordination.",
        ("system:write",),
        server._log_event,
    )
    server.register_tool(
        "system.echo",
        "Echo a payload for integration testing.",
        ("*",),
        server._echo,
    )
    server.register_tool(
        "file_system.list",
        "List files/directories under project root.",
        ("system:read", "system:write"),
        server._file_list,
    )
    server.register_tool(
        "file_system.read",
        "Read a UTF-8 text file under project root.",
        ("system:read", "system:write"),
        server._file_read,
    )
    server.register_tool(
        "file_system.write",
        "Write or append UTF-8 text to a file under project root.",
        ("system:write",),
        server._file_write,
    )
    server.register_tool(
        "github.get_profile",
        "Get authenticated GitHub profile details using JARVIS_GITHUB_TOKEN.",
        ("system:read", "system:write"),
        server._github_get_profile,
    )
    server.register_tool(
        "github.update_profile",
        "Update authenticated GitHub profile fields (supports dry_run).",
        ("system:write",),
        server._github_update_profile,
    )
    return server
