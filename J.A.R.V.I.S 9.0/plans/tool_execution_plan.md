# Implementation Plan: Tool Execution
## What

The Tool Execution feature is a mechanism that enables J.A.R.V.I.S 9.0 to execute various tools, including read, write, cmd, swarm, and claw, with parameters and error handling. This feature involves the following components:

* **Tool Interface**: Defines the contract for tool execution, including parameter passing and error handling.
* **Tool Registry**: Responsible for registering and managing available tools.
* **Tool Executor**: Executes tools with provided parameters and handles errors.
* **Planner Module**: Integrates with the Tool Executor to plan and schedule tool execution.

## Why

J.A.R.V.I.S 9.0 needs the Tool Execution feature to:

* Enhance its capabilities by leveraging existing tools and scripts.
* Provide a flexible and extensible framework for executing various tasks.
* Improve error handling and debugging capabilities.

## How

### Step 1: Create Tool Interface ( `tool_interface.py` )

Create a new file `tool_interface.py` in the `jarvis/core/tools` directory:
```python
# jarvis/core/tools/tool_interface.py

from abc import ABC, abstractmethod

class ToolInterface(ABC):
    @abstractmethod
    def execute(self, params: dict) -> str:
        """Execute the tool with provided parameters."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get the tool name."""
        pass

    @abstractmethod
    def get_description(self) -> str:
        """Get the tool description."""
        pass
```
### Step 2: Implement Tool Registry ( `tool_registry.py` )

Create a new file `tool_registry.py` in the `jarvis/core/tools` directory:
```python
# jarvis/core/tools/tool_registry.py

from jarvis.core.tools.tool_interface import ToolInterface

class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def register_tool(self, tool: ToolInterface):
        self.tools[tool.get_name()] = tool

    def get_tool(self, name: str) -> ToolInterface:
        return self.tools.get(name)
```
### Step 3: Implement Tool Executor ( `tool_executor.py` )

Create a new file `tool_executor.py` in the `jarvis/core/tools` directory:
```python
# jarvis/core/tools/tool_executor.py

from jarvis.core.tools.tool_interface import ToolInterface
from jarvis.core.tools.tool_registry import ToolRegistry

class ToolExecutor:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def execute_tool(self, name: str, params: dict) -> str:
        tool = self.registry.get_tool(name)
        if tool:
            return tool.execute(params)
        else:
            raise ValueError(f"Tool '{name}' not found.")
```
### Step 4: Integrate Tool Executor with Planner Module ( `planner.py` )

Modify the `planner.py` file in the `jarvis/core/planner` directory to integrate with the Tool Executor:
```python
# jarvis/core/planner/planner.py

from jarvis.core.tools.tool_executor import ToolExecutor
from jarvis.core.tools.tool_registry import ToolRegistry

class Planner:
    def __init__(self):
        self.tool_registry = ToolRegistry()
        self.tool_executor = ToolExecutor(self.tool_registry)

    def plan_tool_execution(self, name: str, params: dict):
        self.tool_executor.execute_tool(name, params)
```
### Step 5: Register Tools ( `tools.py` )

Create a new file `tools.py` in the `jarvis/core/tools` directory to register available tools:
```python
# jarvis/core/tools/tools.py

from jarvis.core.tools.tool_interface import ToolInterface
from jarvis.core.tools.tool_registry import ToolRegistry

class ReadTool(ToolInterface):
    def execute(self, params: dict) -> str:
        # Implement read tool execution
        pass

    def get_name(self) -> str:
        return "read"

    def get_description(self) -> str:
        return "Read tool"

class WriteTool(ToolInterface):
    def execute(self, params: dict) -> str:
        # Implement write tool execution
        pass

    def get_name(self) -> str:
        return "write"

    def get_description(self) -> str:
        return "Write tool"

# Register tools
tool_registry = ToolRegistry()
tool_registry.register_tool(ReadTool())
tool_registry.register_tool(WriteTool())
```
### Step 6: Test Tool Execution

Create a test file `test_tool_execution.py` in the `jarvis/core/tests` directory to test tool execution:
```python
# jarvis/core/tests/test_tool_execution.py

from jarvis.core.tools.tool_executor import ToolExecutor
from jarvis.core.tools.tool_registry import ToolRegistry

def test_tool_execution():
    tool_registry = ToolRegistry()
    tool_executor = ToolExecutor(tool_registry)

    # Register tools
    tool_registry.register_tool(ReadTool())
    tool_registry.register_tool(WriteTool())

    # Execute tools
    result = tool_executor.execute_tool("read", {"param1": "value1"})
    assert result == "Read tool executed successfully"

    result = tool_executor.execute_tool("write", {"param2": "value2"})
    assert result == "Write tool executed successfully"
```
This implementation plan integrates the Tool Execution feature from J.A.R.V.I.S 4.0 into J.A.R.V.I.S 9.0's codebase, providing a flexible and extensible framework for executing various tools with parameters and error handling.