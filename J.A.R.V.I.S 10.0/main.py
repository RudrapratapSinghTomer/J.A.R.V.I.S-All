import os
import sys
import asyncio
import shlex
import re
from dotenv import load_dotenv
from openai import OpenAI

# Ensure J.A.R.V.I.S 10.0 core is in the import path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.sandbox import DockerSandbox
from core.cli_engine import CLIEngine
from core.browser import WebBridgeBrowser
from core.capability_acquirer import CapabilityAcquirer
from core.memory import SystemContextMemory, AgentMemory
from core.planner import CognitivePlanner
from core.orchestrator import DualLoopOrchestrator
from core.plugin_manager import PluginManager
from core.persona import PersonaEngine, get_persona  # Phase 1: persona & context injection
from core.audio_pipeline import Ears, FishSpeechClient  # Phase 2: audio pipeline
from core.vision import VisionAnalyzer

def print_banner():
    print("\n" + "=" * 60)
    print("      J.A.R.V.I.S 10.0 — Universal Agentic Core (Project X)")
    print("=" * 60)
    print("  Capabilities:")
    print("    • Dual-Loop Parallel Validation Orchestrator")
    print("    • Self-Validating CLI with Sandbox Subprocess Fallback")
    print("    • Multi-Layer STM/LTM & High-Level System Context Memory")
    print("    • Kimi WebBridge Browser & Document Scraping")
    print("    • Human-in-the-Loop Capability Acquisition Plan Review")
    print("=" * 60)
    print("  Special Command Syntax:")
    print("    propose <capability>             — Autonomous research & draft integration plan")
    print("    approve <capability>             — Confirm and execute approved capability installation")
    print("    search antigravity <term>        — Search the Antigravity awesome-skills library")
    print("    propose antigravity <skill>      — Propose dynamic integration of a pre-built skill")
    print("    approve antigravity <skill>      — Synthesize, validate, and activate pre-built skill")
    print("    browser <action> <args>          — Kimi browser control (navigate, click, fill, screenshot, pdf, close)")
    print("    plugin run <name> <args>         — Run a dynamically loaded plugin")
    print("    exit / quit                      — Shut down")
    print("=" * 60 + "\n")

def get_user_input(prompt: str) -> str:
    try:
        return input(prompt)
    except (KeyboardInterrupt, EOFError):
        return "exit"

async def main():
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
    print_banner()

    # 1. Initialize NVIDIA Cloud LLM Client if API Key is available
    nvidia_key = os.getenv("NVIDIA_API_KEY")
    llm_client = None
    model_name = os.getenv("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct")
    
    if nvidia_key:
        try:
            llm_client = OpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=nvidia_key
            )
            print("[System] Cloud LRM Client initialized successfully.")
        except Exception as e:
            print(f"[System Warning] Failed to initialize Cloud LRM Client: {e}")
    else:
        print("[System Info] NVIDIA_API_KEY not found in environment. Operating in offline/local-fallback mode.")

    # 2. Build Core Subsystems
    workspace_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
    
    sandbox = DockerSandbox()
    cli_engine = CLIEngine(sandbox, llm_client, model=model_name)
    browser = WebBridgeBrowser(llm_client=llm_client, model=model_name)
    if browser.is_kimi_active():
        print("[System] Kimi WebBridge local daemon: ACTIVE and responsive!")
    else:
        print("[System Warning] Kimi WebBridge local daemon: OFFLINE. Operating in fallback search mode.")
    acquirer = CapabilityAcquirer(browser, cli_engine, llm_client, model=model_name)
    
    sys_memory = SystemContextMemory(workspace_root, sandbox=sandbox)
    agent_memory = AgentMemory("CoreOrchestrator")
    plugin_manager = PluginManager(os.path.dirname(__file__))
    
    # Initialize dynamic hardware vision analyzer
    vision_analyzer = VisionAnalyzer(llm_client=llm_client, cloud_model="meta/llama-3.2-90b-vision-instruct", local_model="llama3.2-vision:11b")
    
    planner = CognitivePlanner(llm_client, model=model_name)
    orchestrator = DualLoopOrchestrator(
        planner=planner,
        cli_engine=cli_engine,
        sys_memory=sys_memory,
        agent_memory=agent_memory,
        llm_client=llm_client,
        model=model_name,
        browser=browser,
        acquirer=acquirer,
        plugin_manager=plugin_manager,
        vision=vision_analyzer
    )

    user_id = os.getenv("JARVIS_USER", "developer")

    # Phase 1: Initialise & validate the Persona Engine (reads user_vault.md)
    print("\n[Phase 1] Initialising Core Persona & Context Injection...")
    persona = get_persona()  # Singleton — also used by orchestrator & cognitive engine
    print(f"[Phase 1] Persona engine active. User vault loaded.")
    print(f"[Phase 1] Greeting user: {user_id}")
    print("[Phase 1] J.A.R.V.I.S persona: ONLINE — British. Polite. Witty.\n")

    # Initialize Audio Subsystems
    speech_client = FishSpeechClient()
    voice_enabled = "--voice" in sys.argv
    speech_client.enabled = voice_enabled
    ears = None

    async def execute_query_workflow(query_text: str):
        nonlocal voice_enabled, ears
        query_text = query_text.strip()
        if not query_text:
            return

        if query_text.lower() in ["exit", "quit"]:
            print("[JARVIS] Gracefully stopping sandbox container. Goodbye sir.")
            sandbox.stop_container()
            if ears:
                ears.stop()
            sys.exit(0)

        # --- Human-in-the-Loop Capability Hooks ---
        if query_text.lower().startswith("search antigravity "):
            term = query_text[len("search antigravity "):].strip()
            if not term:
                print("[JARVIS] Please specify a search term. E.g. 'search antigravity detection'")
                return
            
            print(f"[JARVIS] Searching Antigravity library for '{term}'...")
            results = acquirer.antigravity_loader.filter_skills_by_query(term)
            if not results:
                print(f"[JARVIS] No matching skills found in Antigravity library.")
            else:
                msg = f"I found {len(results)} matching skills in the Antigravity library, sir."
                print(f"[JARVIS] {msg}")
                if voice_enabled:
                    asyncio.create_task(speech_client.speak(msg, "calm"))
                print("\n" + "=" * 80)
                print(f"                 ANTIGRAVITY AWESOME SKILLS MATCHES FOR: '{term}'")
                print("=" * 80)
                for skill in results[:10]:
                    meta = skill.get("metadata", {})
                    desc = meta.get("description", "No description.")
                    print(f" • [Skill] : {skill['name']}")
                    print(f"   [Desc]  : {desc[:100]}...")
                    print(f"   [Risk]  : {meta.get('risk', 'unknown')}")
                    print("-" * 80)
                if len(results) > 10:
                    print(f" ... and {len(results) - 10} more matches.")
                print("=" * 80 + "\n")
            return

        elif query_text.lower().startswith("propose antigravity "):
            skill = query_text[len("propose antigravity "):].strip()
            if not skill:
                print("[JARVIS] Please specify a skill name. E.g. 'propose antigravity ad-creative'")
                return
            
            print(f"[JARVIS] Initiating Antigravity research & planning for '{skill}'...")
            plan_path = acquirer.propose_antigravity_skill_integration(skill)
            
            if plan_path:
                msg = f"SUCCESS: Antigravity Skill Integration Plan created for {skill}!"
                print(f"\n[JARVIS] {msg}")
                print(f"[JARVIS] Location: {plan_path}")
                print(f"[JARVIS] Please review the plan in your editor. When satisfied, run: 'approve antigravity {skill}'\n")
                if voice_enabled:
                    asyncio.create_task(speech_client.speak(f"I have successfully created an integration plan for {skill}, sir. Please review it.", "calm"))
            else:
                msg = f"Failed to create plan. Ensure skill '{skill}' exists in the library."
                print(f"[JARVIS] {msg}\n")
                if voice_enabled:
                    asyncio.create_task(speech_client.speak(msg, "serious"))
            return

        elif query_text.lower().startswith("approve antigravity "):
            skill = query_text[len("approve antigravity "):].strip()
            if not skill:
                print("[JARVIS] Please specify the skill name to approve. E.g. 'approve antigravity ad-creative'")
                return
            
            safe_name = skill.lower().replace(" ", "_").replace("-", "_")
            plan_filename = f"antigravity_{safe_name}_plan.json"
            plan_path = os.path.normpath(os.path.join(workspace_root, "J.A.R.V.I.S 10.0", "capabilities", "plans", plan_filename))
            
            if not os.path.exists(plan_path):
                msg = f"No active Antigravity draft plan found for '{skill}'"
                print(f"[JARVIS] {msg} at: {plan_path}")
                if voice_enabled:
                    asyncio.create_task(speech_client.speak(msg, "serious"))
                return
                
            print(f"[JARVIS] Executing approved Antigravity skill installation for '{skill}'...")
            res = acquirer.execute_antigravity_skill_installation(plan_path)
            
            if res.get("success"):
                msg = f"SUCCESS: {res.get('message')}. Registry updated. Dynamic Antigravity skill '{skill}' is now natively active!"
                print(f"\n[JARVIS] {msg}\n")
                if voice_enabled:
                    asyncio.create_task(speech_client.speak(f"Dynamic skill {skill} is now active, sir.", "excited"))
            else:
                msg = f"FAILED: {res.get('error')}"
                print(f"\n[JARVIS] {msg}\n")
                if voice_enabled:
                    asyncio.create_task(speech_client.speak(f"Installation failed, sir: {res.get('error')}", "serious"))
            return

        elif query_text.lower().startswith("propose "):
            capability = query_text[len("propose "):].strip()
            if not capability:
                print("[JARVIS] Please specify a capability name. E.g. 'propose Image Classification'")
                return
                
            print(f"[JARVIS] Initiating dynamic research for '{capability}'...")
            plan_path = acquirer.propose_capability_plan(capability, "Acquire capability matching user request")
            
            if plan_path:
                msg = f"SUCCESS: Integration Plan checklist created for {capability}!"
                print(f"\n[JARVIS] {msg}")
                print(f"[JARVIS] Location: {plan_path}")
                print(f"[JARVIS] Please review the plan in your editor. When satisfied, run: 'approve {capability}'\n")
                if voice_enabled:
                    asyncio.create_task(speech_client.speak(f"I have proposed a capability plan for {capability}, sir.", "calm"))
            else:
                msg = f"FAILED: Could not generate integration plan for '{capability}'."
                print(f"\n[JARVIS] {msg}\n")
                if voice_enabled:
                    asyncio.create_task(speech_client.speak(msg, "serious"))
            return

        elif query_text.lower().startswith("approve "):
            capability = query_text[len("approve "):].strip()
            if not capability:
                print("[JARVIS] Please specify the capability name to approve. E.g. 'approve Image Classification'")
                return
                
            plan_filename = f"{capability.lower().replace(' ', '_')}_plan.json"
            plan_path = os.path.normpath(os.path.join(workspace_root, "J.A.R.V.I.S 10.0", "capabilities", "plans", plan_filename))
            
            if not os.path.exists(plan_path):
                msg = f"No active draft plan found for '{capability}'"
                print(f"[JARVIS] {msg} at: {plan_path}")
                if voice_enabled:
                    asyncio.create_task(speech_client.speak(msg, "serious"))
                return
                
            print(f"[JARVIS] Executing approved capability installation for '{capability}'...")
            res = acquirer.execute_and_install_capability(plan_path)
            
            if res.get("success"):
                msg = f"SUCCESS: {res.get('message')}. Registry updated. New skill '{capability}' is now natively active!"
                print(f"\n[JARVIS] {msg}\n")
                if voice_enabled:
                    asyncio.create_task(speech_client.speak(f"New skill {capability} successfully registered, sir.", "excited"))
            else:
                msg = f"FAILED: {res.get('error')}"
                print(f"\n[JARVIS] {msg}\n")
                if voice_enabled:
                    asyncio.create_task(speech_client.speak(f"Installation failed: {res.get('error')}", "serious"))
            return

        # --- Kimi WebBridge Browser Interactive Routing Hooks ---
        elif query_text.lower().startswith("browser "):
            cmd_parts = query_text[len("browser "):].strip().split(" ", 1)
            subcmd = cmd_parts[0].lower()
            args_str = cmd_parts[1].strip() if len(cmd_parts) > 1 else ""

            if not browser.is_kimi_active():
                msg = "Error: Kimi WebBridge local daemon is offline. Cannot execute browser commands."
                print(f"[JARVIS] {msg}")
                if voice_enabled:
                    asyncio.create_task(speech_client.speak(msg, "serious"))
                return

            if subcmd == "navigate":
                url = args_str
                if not url:
                    print("[JARVIS] Please specify a URL or search instruction. E.g. 'browser navigate to wikipedia'")
                    return
                print(f"[JARVIS] Navigating to '{url}'...")
                res = browser.smart_navigate(url)
                if res.get("success"):
                    msg = res.get("message", "Navigated successfully.")
                    print(f"[JARVIS] SUCCESS: {msg}")
                    if voice_enabled:
                        asyncio.create_task(speech_client.speak(f"Successfully loaded the page at {url}, sir.", "calm"))
                else:
                    print(f"[JARVIS] FAILED: {res.get('error')}")
                    if voice_enabled:
                        asyncio.create_task(speech_client.speak(f"Failed to navigate: {res.get('error')}", "serious"))

            elif subcmd == "click":
                selector = args_str
                if not selector:
                    print("[JARVIS] Please specify an element selector. E.g. 'browser click #submit'")
                    return
                print(f"[JARVIS] Clicking element '{selector}'...")
                res = browser.click(selector)
                if res.get("success"):
                    print("[JARVIS] SUCCESS: Clicked successfully.")
                    if voice_enabled:
                        asyncio.create_task(speech_client.speak("Clicked.", "calm"))
                else:
                    print(f"[JARVIS] FAILED: {res.get('error')}")

            elif subcmd == "fill":
                try:
                    fill_tokens = shlex.split(args_str)
                except ValueError:
                    fill_tokens = args_str.split(" ", 1)
                
                if len(fill_tokens) < 2 or not fill_tokens[0] or not fill_tokens[1]:
                    print("[JARVIS] Please specify selector and value. E.g. 'browser fill \"input[name=q]\" \"hello world\"'")
                    return
                
                selector, value = fill_tokens[0], " ".join(fill_tokens[1:])

                print(f"[JARVIS] Filling '{selector}' with '{value}'...")
                res = browser.fill(selector, value)
                if res.get("success"):
                    print("[JARVIS] SUCCESS: Element filled successfully.")
                else:
                    print(f"[JARVIS] FAILED: {res.get('error')}")

            elif subcmd == "screenshot":
                print("[JARVIS] Capturing screenshot...")
                selector = args_str if args_str else None
                res = browser.screenshot(selector=selector)
                if res.get("success"):
                    print(f"[JARVIS] SUCCESS: Screenshot saved at '{res.get('path')}'")
                else:
                    print(f"[JARVIS] FAILED: {res.get('error')}")

            elif subcmd == "pdf":
                print("[JARVIS] Rendering current browser window into PDF...")
                file_name = args_str if args_str else None
                res = browser.save_as_pdf(file_name=file_name)
                if res.get("success"):
                    print(f"[JARVIS] SUCCESS: PDF saved at '{res.get('path')}'")
                else:
                    print(f"[JARVIS] FAILED: {res.get('error')}")

            elif subcmd == "close":
                print("[JARVIS] Closing active browser session...")
                res = browser.close_session()
                if res.get("success"):
                    print("[JARVIS] SUCCESS: Session closed.")
                else:
                    print(f"[JARVIS] FAILED: {res.get('error')}")
            else:
                # Fallback unrecognized commands to smart navigate/search
                full_args = query_text[len("browser "):].strip()
                print(f"[JARVIS] Processing smart browser action: '{full_args}'...")
                res = browser.smart_navigate(full_args)
                if res.get("success"):
                    msg = res.get("message", "Completed successfully.")
                    print(f"[JARVIS] SUCCESS: {msg}")
                else:
                    print(f"[JARVIS] FAILED: {res.get('error')}")
            return

        elif query_text.lower().startswith("plugin run "):
            # Extract the plugin name and arguments
            args = query_text[11:].strip()
            if not args:
                print("[JARVIS] Please specify a plugin name. E.g. 'plugin run ad_creative'")
                return
            parts = args.split(" ", 1)
            plugin_name = parts[0]
            plugin_args = parts[1] if len(parts) > 1 else ""
            
            print(f"[JARVIS] Executing plugin '{plugin_name}' with args: {plugin_args}")
            inputs = {"query": plugin_args}
            res = plugin_manager.execute_plugin(plugin_name, inputs)
            
            if res.get("success"):
                print(f"\n[JARVIS] Plugin Execution Success:")
                print(res.get("message", res))
            else:
                print(f"\n[JARVIS] Plugin Execution Failed: {res.get('error')}")
            return

        # --- Standard Query Orchestration Loop ---
        print("\n[Jarvis Processing...]\n")
        
        # Populate STM with user query for multi-turn context
        agent_memory.add_to_stm("user", query_text)
        
        # Run query asynchronously through parallelized orchestrator
        response = await orchestrator.run(query_text, user_id=user_id)
        
        # Store response in STM for conversation continuity
        agent_memory.add_to_stm("assistant", response)
        
        # Parse emotion tag from response, e.g. "[excited] Understood, sir."
        emotion = "calm"
        cleaned_res = response
        tag_match = re.match(r"^\[([a-zA-Z\s_]+)\]\s*(.*)$", response)
        if tag_match:
            emotion = tag_match.group(1).lower().strip()
            cleaned_res = tag_match.group(2).strip()

        print(f"\n[JARVIS]> {response}\n")

        # Synthesize audio output if voice synthesis is active
        if voice_enabled:
            asyncio.create_task(speech_client.speak(cleaned_res, emotion))

    # Start audio systems immediately if requested via startup flag
    if voice_enabled:
        print("[System] Voice mode enabled at startup. Initiating voice subsystems...")
        loop = asyncio.get_running_loop()
        def on_transcribe(text):
            print(f"\n[Ears Transcription]> {text}")
            asyncio.run_coroutine_threadsafe(
                execute_query_workflow(text), loop
            )
        ears = Ears(on_transcription=on_transcribe)
        ears_started = ears.start()
        if ears_started:
            print("[JARVIS] Vocal systems and auditory sensors online, sir.")
        else:
            print("[JARVIS Warning] Auditory sensor initialization failed, but vocal output is active, sir.")

    # 3. Main Command Loop
    while True:
        try:
            loop = asyncio.get_running_loop()
            query = await loop.run_in_executor(None, get_user_input, f"[{user_id}]> ")
            query = query.strip()
            
            if not query:
                continue

            if query.lower() == "/voice":
                voice_enabled = not voice_enabled
                speech_client.enabled = voice_enabled
                if voice_enabled:
                    print("[System] Voice mode enabled. Initiating voice subsystems...")
                    if ears is None:
                        loop = asyncio.get_running_loop()
                        def on_transcribe(text):
                            print(f"\n[Ears Transcription]> {text}")
                            asyncio.run_coroutine_threadsafe(
                                execute_query_workflow(text), loop
                            )
                        ears = Ears(on_transcription=on_transcribe)
                    
                    ears_started = ears.start()
                    if ears_started:
                        print("[JARVIS] Vocal systems and auditory sensors online, sir.")
                    else:
                        print("[JARVIS Warning] Auditory sensor initialization failed, but vocal output is active, sir.")
                else:
                    print("[System] Voice mode disabled.")
                    if ears:
                        ears.stop()
                continue

            await execute_query_workflow(query)

        except KeyboardInterrupt:
            print("\n[JARVIS] Interrupted. Goodbye.")
            sandbox.stop_container()
            if ears:
                ears.stop()
            break
        except Exception as e:
            print(f"\n[System Error] {e}\n")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
