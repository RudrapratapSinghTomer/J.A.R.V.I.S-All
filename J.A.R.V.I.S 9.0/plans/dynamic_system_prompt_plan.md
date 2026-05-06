# Implementation Plan: Dynamic System Prompt
## What
The Dynamic System Prompt feature is a mechanism that generates a dynamic prompt that injects environment context to prevent OS-hallucinations. This feature is implemented through the `system_prompt` variable in the `SequenceArchitect` class. The feature involves the following components:

* `SequenceArchitect` class: responsible for generating the dynamic prompt
* `EnvironmentContext` class: provides the environment context to be injected into the prompt
* `OSInterface` class: interacts with the operating system to retrieve relevant information

## Why
J.A.R.V.I.S 9.0 needs this feature to improve its interaction with the operating system and prevent OS-hallucinations. The dynamic prompt provides context to the system, allowing it to better understand the environment and make more informed decisions. This feature is essential for J.A.R.V.I.S 9.0 to achieve its goal of seamless integration with the operating system.

## How
### Step 1: Create the EnvironmentContext class

Create a new file `environment_context.py` in the `jarvis/core` directory:
```python
# jarvis/core/environment_context.py

class EnvironmentContext:
    def __init__(self):
        self.context = {}

    def update_context(self, key, value):
        self.context[key] = value

    def get_context(self):
        return self.context
```
### Step 2: Update the SequenceArchitect class

Update the `sequence_architect.py` file in the `jarvis/core` directory to include the `system_prompt` variable:
```python
# jarvis/core/sequence_architect.py

from jarvis.core.environment_context import EnvironmentContext

class SequenceArchitect:
    def __init__(self):
        self.system_prompt = ""
        self.environment_context = EnvironmentContext()

    def generate_prompt(self):
        # Generate the dynamic prompt using the environment context
        self.system_prompt = f"{self.environment_context.get_context()}> "
        return self.system_prompt
```
### Step 3: Integrate with the OSInterface class

Update the `os_interface.py` file in the `jarvis/core` directory to interact with the `SequenceArchitect` class:
```python
# jarvis/core/os_interface.py

from jarvis.core.sequence_architect import SequenceArchitect

class OSInterface:
    def __init__(self):
        self.sequence_architect = SequenceArchitect()

    def get_prompt(self):
        return self.sequence_architect.generate_prompt()
```
### Step 4: Update the Planner module

Update the `planner.py` file in the `jarvis/modules` directory to use the dynamic prompt:
```python
# jarvis/modules/planner.py

from jarvis.core.os_interface import OSInterface

class Planner:
    def __init__(self):
        self.os_interface = OSInterface()

    def plan(self):
        # Use the dynamic prompt to plan the next action
        prompt = self.os_interface.get_prompt()
        # ...
```
### Step 5: Test the feature

Create a test file `test_dynamic_prompt.py` in the `jarvis/tests` directory:
```python
# jarvis/tests/test_dynamic_prompt.py

from jarvis.core.sequence_architect import SequenceArchitect

def test_dynamic_prompt():
    sequence_architect = SequenceArchitect()
    environment_context = EnvironmentContext()
    environment_context.update_context("key", "value")
    sequence_architect.environment_context = environment_context
    prompt = sequence_architect.generate_prompt()
    assert prompt == "{key: value}> "
```
Run the test using the `pytest` command:
```bash
pytest jarvis/tests/test_dynamic_prompt.py
```
This implementation plan integrates the Dynamic System Prompt feature from J.A.R.V.I.S 7.0 into J.A.R.V.I.S 9.0. The feature is implemented through the `system_prompt` variable in the `SequenceArchitect` class, which generates a dynamic prompt that injects environment context to prevent OS-hallucinations.