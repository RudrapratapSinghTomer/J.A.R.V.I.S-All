import asyncio
import json
import os
import time
from loguru import logger


async def test_ruflo():
    cli_path = "c:/Users/developer/Desktop/J.A.R.V.I.S All/J.A.R.V.I.S/scratch/ruflo/v3/@claude-flow/cli/bin/cli.js"

    print(f"Connecting to: {cli_path}")

    proc = await asyncio.create_subprocess_exec(
        "node",
        cli_path,
        "mcp",
        "start",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # Wait for init
    await asyncio.sleep(2)

    # Request tools list first to see if it's alive
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}

    try:
        print("Sending tools/list...")
        proc.stdin.write(json.dumps(request).encode() + b"\n")
        await proc.stdin.drain()

        # Read until we have at least one full JSON object or timeout
        response_raw = b""
        start_time = time.time()
        while time.time() - start_time < 5:
            chunk = await proc.stdout.read(1024 * 1024)  # 1MB chunks
            if not chunk:
                break
            response_raw += chunk
            if b"}" in chunk:
                break

        if not response_raw:
            print("No response from server stdout.")
            stderr = await proc.stderr.read()
            print(f"Stderr output: {stderr.decode()}")
        else:
            text = response_raw.decode(errors="ignore")
            # Find the JSON part
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                try:
                    response = json.loads(text[start : end + 1])
                    print("Response received!")
                    tools = response.get("result", {}).get("tools", [])
                    print(f"Available tools count: {len(tools)}")
                    all_tool_names = [t["name"] for t in tools]
                    print(f"First 10 tools: {all_tool_names[:10]}")
                    if "execute_task" in all_tool_names:
                        print("SUCCESS: 'execute_task' tool found!")
                    else:
                        print("WARNING: 'execute_task' tool NOT found.")
                        # Find similar tools
                    # Query details for task_create
                    print("\nFetching definition for 'task_create'...")
                    detail_req = {
                        "jsonrpc": "2.0",
                        "id": 2,
                        "method": "tools/call",
                        "params": {"name": "task_create", "arguments": {"help": True}},
                    }
                    # Actually, tools/list already returns schemas in some MCP implementations.
                    # Let's just find them in the 'tools' list.
                    target_tools = ["task_create", "agent_execute", "swarm_init"]
                    for t in tools:
                        if t["name"] in target_tools:
                            print(f"\nTool: {t['name']}")
                            print(f"Description: {t.get('description')}")
                            print(
                                f"Input Schema: {json.dumps(t.get('inputSchema'), indent=2)}"
                            )
                except json.JSONDecodeError as e:
                    print(f"JSON Decode Error: {e}")
                    print(f"Buffer size: {len(text)}")
                    print(
                        f"Fragment: {text[start : start + 100]} ... {text[end - 100 : end + 1]}"
                    )
            else:
                print(
                    f"Could not find valid JSON in response. Buffer size: {len(text)}"
                )

    except Exception as e:
        print(f"Error during communication: {e}")
    finally:
        try:
            proc.terminate()
            await proc.wait()
        except ProcessLookupError:
            pass


if __name__ == "__main__":
    asyncio.run(test_ruflo())
