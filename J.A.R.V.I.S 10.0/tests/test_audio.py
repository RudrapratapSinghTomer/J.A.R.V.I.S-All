import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add parent directory to path
sys.path.append(os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from core.audio_pipeline import UserStateDetector, FishSpeechClient, Ears
from core.orchestrator import DualLoopOrchestrator
from core.planner import CognitivePlanner
from core.cli_engine import CLIEngine
from core.memory import SystemContextMemory, AgentMemory

def main():
    print("=== Testing J.A.R.V.I.S 10.0 Audio & Urgency Pipeline ===")
    failed = False

    # 1. Test UserStateDetector
    print("\n[Test 1] Testing UserStateDetector for emotions and urgency...")
    
    # Explicit tags
    state = UserStateDetector.detect("[excited] Hello, how are you?")
    assert state["emotion"] == "excited"
    assert state["urgency"] == "normal"
    assert state["text"] == "Hello, how are you?"
    
    state = UserStateDetector.detect("[hurry] check system status")
    assert state["emotion"] == "serious"
    assert state["urgency"] == "high"
    assert state["text"] == "check system status"
    
    # Implicit keywords for urgency
    state = UserStateDetector.detect("asap run the test script!")
    assert state["urgency"] == "high"
    assert state["emotion"] == "serious"
    
    # Implicit keywords for excitement
    state = UserStateDetector.detect("This is awesome and fantastic!")
    assert state["emotion"] == "excited"
    
    # Implicit keywords for worry/troubleshooting
    state = UserStateDetector.detect("My application crashed with an error")
    assert state["emotion"] == "serious"
    
    print("[SUCCESS] UserStateDetector correctly parsed all states and stripped tags!")

    # 2. Test FishSpeechClient
    print("\n[Test 2] Testing FishSpeechClient prep/fallbacks...")
    client = FishSpeechClient(api_key="mock_key", enabled=True)
    
    # Test prepare_text
    prepared = client.prepare_text("[excited] Thank you very much, sir.", "excited")
    assert "[excited]" in prepared
    assert prepared.count("[excited]") == 1  # Verify it stripped the duplicate and prepended correctly
    
    # Test fallback speak mechanism
    with patch("core.audio_pipeline.urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = b"RIFFmockaudiobytes"
        mock_urlopen.return_value.__enter__.return_value = mock_response
        
        with patch("sounddevice.play") as mock_sd_play, patch("sounddevice.wait") as mock_sd_wait:
            with patch("scipy.io.wavfile.read") as mock_wav_read:
                mock_wav_read.return_value = (16000, MagicMock())
                
                # Verify that it synthesizes and plays successfully
                async def run_speak():
                    return await client.speak("Hello there", "calm")
                
                import asyncio
                res = asyncio.run(run_speak())
                assert res is True
                
    print("[SUCCESS] FishSpeechClient successfully prepared text and executed vocal playback fallback!")

    # 3. Test Orchestrator bypass routing for simple queries
    print("\n[Test 3] Testing DualLoopOrchestrator simple query bypass...")
    planner = CognitivePlanner()
    cli_engine = CLIEngine(None)
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    sys_memory = SystemContextMemory(workspace_dir)
    agent_memory = AgentMemory("TestAudioOrchestrator")
    
    # Clean LTM
    if os.path.exists(agent_memory.ltm_path):
        os.remove(agent_memory.ltm_path)
    agent_memory = AgentMemory("TestAudioOrchestrator")

    orchestrator = DualLoopOrchestrator(
        planner=planner,
        cli_engine=cli_engine,
        sys_memory=sys_memory,
        agent_memory=agent_memory
    )
    
    # Greetings should NOT be complex
    assert orchestrator._is_query_complex("Hi jarvis") is False
    assert orchestrator._is_query_complex("Hello, J.A.R.V.I.S.") is False
    assert orchestrator._is_query_complex("good morning") is False
    
    # Simple actions should NOT be complex
    assert orchestrator._is_query_complex("open notepad") is False
    assert orchestrator._is_query_complex("play rolling in the deep") is False
    
    # Complex query should be classified as COMPLEX by mocking the LLM classifier
    orchestrator.llm_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = '{"complexity": "COMPLEX", "reason": "Requires system execution"}'
    orchestrator.llm_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])
    
    assert orchestrator._is_query_complex("write a python script to parse logs and deploy to k8s") is True

    print("[SUCCESS] Direct bypass heuristics correctly routed simple vs complex queries!")

    # 4. Test Orchestrator direct action execution (browser navigation & open system app)
    print("\n[Test 4] Testing direct action executing triggers...")
    
    mock_browser = MagicMock()
    mock_browser.smart_navigate.return_value = {"success": True, "message": "Loaded"}
    orchestrator.browser = mock_browser
    
    # Test YouTube play direct action
    import asyncio
    direct_res = asyncio.run(orchestrator._execute_direct_action("play Adele Hello"))
    assert direct_res is not None
    assert " Adele Hello" in direct_res or "Adele Hello" in direct_res
    assert mock_browser.smart_navigate.called
    
    # Test open URL direct action
    mock_browser.smart_navigate.reset_mock()
    direct_res = asyncio.run(orchestrator._execute_direct_action("open google.com"))
    assert direct_res is not None
    assert "google.com" in direct_res
    assert mock_browser.smart_navigate.called
    
    print("[SUCCESS] Orchestrator successfully processed simple action bypass commands!")

    print("\n=======================================================")
    print("  ALL PHASE 2 AUDIO PIPELINE TESTS PASSED!")
    print("=======================================================\n")

if __name__ == "__main__":
    main()
